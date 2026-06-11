"""
関連記事の抽出。

既存の公開記事（src/content/blog/*.md）の frontmatter を読み、いま生成中の
記事に対してカテゴリ一致・タグ重複でスコアリングして上位 2〜3 件を返す。

末尾「## 関連記事」セクション（render.py が組み立て）と、本文中の自動言及
リンク化の両方の materialprovider として使う。

frontmatter は既存記事が `key: 'value'` 形式のシンプルな YAML サブセットしか
使っていないため、PyYAML に依存せず正規表現で読む（パイプライン全体の依存を
増やさない）。tags は `["a", "b"]` 形式と YAML リスト形式の両方を許容する。
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence

LOG = logging.getLogger(__name__)

# 記事 URL のプレフィクス（Astro: src/content/blog/{stem}.md → /blog/{stem}/）
BLOG_URL_PREFIX = "/blog"

_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_INLINE_LIST_RE = re.compile(r"^\[(.*)\]$")


@dataclass
class Post:
    """関連記事スコアリングに使う最小限の記事メタ。"""
    slug: str                       # ファイル名 stem（= Astro の記事 id / URL 末尾）
    title: str
    category: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    pub_date: Optional[datetime] = None

    @property
    def url(self) -> str:
        return f"{BLOG_URL_PREFIX}/{self.slug}/"


# ---------------------------------------------------------------------------
# Frontmatter 解析（YAML サブセット）
# ---------------------------------------------------------------------------
def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        inner = v[1:-1]
        # YAML 単一引用符内の '' エスケープを ' に戻す
        return inner.replace("''", "'") if v[0] == "'" else inner
    return v


def _parse_tags_block(raw_block: str) -> List[str]:
    """`tags:` 行（インライン or リスト形式）からタグ配列を抽出。"""
    # インライン: tags: ["a", "b"]
    m = re.search(r"^tags:\s*(\[.*\])\s*$", raw_block, re.MULTILINE)
    if m:
        inner = _INLINE_LIST_RE.match(m.group(1).strip())
        if inner:
            parts = [p.strip() for p in inner.group(1).split(",")]
            return [_unquote(p) for p in parts if p.strip()]
    # YAML リスト形式:
    #   tags:
    #     - a
    #     - b
    tags: List[str] = []
    lines = raw_block.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^tags:\s*$", line):
            for follow in lines[i + 1:]:
                lm = re.match(r"^\s*-\s+(.*)$", follow)
                if not lm:
                    break
                tags.append(_unquote(lm.group(1)))
            break
    return tags


def _parse_pubdate(value: str) -> Optional[datetime]:
    raw = _unquote(value)
    for fmt in ("%b %d %Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_frontmatter(text: str, slug: str) -> Optional[Post]:
    """記事本文（frontmatter 込み）から Post を組み立てる。失敗時 None。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    block = m.group(1)

    def field_value(key: str) -> str:
        fm = re.search(rf"^{re.escape(key)}:\s*(.*)$", block, re.MULTILINE)
        return _unquote(fm.group(1)) if fm else ""

    title = field_value("title")
    category = field_value("category")
    if not title or not category:
        return None
    return Post(
        slug=slug,
        title=title,
        category=category,
        description=field_value("description"),
        tags=_parse_tags_block(block),
        pub_date=_parse_pubdate(
            re.search(r"^pubDate:\s*(.*)$", block, re.MULTILINE).group(1)
        ) if re.search(r"^pubDate:\s*(.*)$", block, re.MULTILINE) else None,
    )


def load_existing_posts(blog_dir: str) -> List[Post]:
    """src/content/blog/*.md を走査して Post のリストを返す。"""
    posts: List[Post] = []
    if not os.path.isdir(blog_dir):
        LOG.warning("blog_dir not found: %s", blog_dir)
        return posts
    for name in sorted(os.listdir(blog_dir)):
        if not name.endswith(".md") and not name.endswith(".mdx"):
            continue
        slug = re.sub(r"\.mdx?$", "", name)
        path = os.path.join(blog_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            LOG.warning("Cannot read %s: %s", path, e)
            continue
        post = parse_frontmatter(text, slug)
        if post:
            posts.append(post)
    LOG.info("Loaded %d existing posts from %s", len(posts), blog_dir)
    return posts


# ---------------------------------------------------------------------------
# スコアリング
# ---------------------------------------------------------------------------
# カテゴリ一致の重み。タグ 1 個重複より十分大きくし「同カテゴリ優先」にする。
CATEGORY_MATCH_WEIGHT = 3
TAG_OVERLAP_WEIGHT = 2


def score_relevance(post: Post, category: str, tags: Sequence[str]) -> int:
    """post の、対象記事（category, tags）に対する関連度スコア。"""
    score = 0
    if post.category == category:
        score += CATEGORY_MATCH_WEIGHT
    overlap = len(set(post.tags) & set(tags or []))
    score += overlap * TAG_OVERLAP_WEIGHT
    return score


def find_related_posts(
    category: str,
    tags: Sequence[str],
    all_posts: Sequence[Post],
    *,
    exclude_slug: str = "",
    limit: int = 3,
    min_score: int = 1,
) -> List[Post]:
    """カテゴリ・タグマッチで関連記事を上位 limit 件返す。

    Args:
        category:     対象記事のカテゴリ
        tags:         対象記事のタグ
        all_posts:    既存記事（load_existing_posts の結果）
        exclude_slug: 自分自身の slug（除外）
        limit:        最大件数（HANDOFF: 2〜3）
        min_score:    これ未満のスコアは無関係として捨てる

    Returns:
        スコア降順・同点は新しい記事順。該当なしなら空リスト
        （フォールバック: 関連記事セクションを出さない）。
    """
    scored = []
    for p in all_posts:
        if p.slug == exclude_slug:
            continue
        s = score_relevance(p, category, tags)
        if s >= min_score:
            scored.append((s, p))

    # スコア降順 → pub_date 降順（None は最古扱い）
    def sort_key(item):
        s, p = item
        ts = p.pub_date.timestamp() if p.pub_date else 0.0
        return (s, ts)

    scored.sort(key=sort_key, reverse=True)
    return [p for _, p in scored[:limit]]
