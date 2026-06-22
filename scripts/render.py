"""
記事 JSON → src/content/blog/{YYYY-MM-DD}-{slug}.md ファイル化。

- frontmatter: title, description, pubDate (Astro 形式の 'May 30 2026'), category, heroImage(任意)
- 本文先頭に PR 表記を強制挿入
- アフィリエイトトークンを実 HTML に置換
- slug は title から英数字化 / ハッシュで一意化
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from scripts.affiliates import format_inline_affiliate, prepend_pr_notice, replace_tokens

LOG = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOG_DIR = os.path.join(REPO_ROOT, "src", "content", "blog")

VALID_CATEGORIES = {"整備の現場", "越境EC事業", "AI・自動化", "対馬ライフ"}

# H2 行（`## 見出し`）。`### ` 以下や `#`（H1）は対象外。
_H2_RE = re.compile(r"^##\s+(?!#)(.+?)\s*$")

# 末尾の定型 H2（画像やインラインアフィを差し込みたくない見出し）。
# enrichment 対象から外して、本文セクションだけをリッチ化する。
_SKIP_ENRICH_HEADINGS = ("まとめ", "参考", "関連記事", "関連サービス")

# コードフェンス開始/終了行（``` と ~~~ の両方）。フェンス内の `## ` は見出し扱いしない。
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _is_fence_line(line: str) -> bool:
    return bool(_FENCE_RE.match(line))


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------
def slugify(title: str, date_str: str) -> str:
    """日本語タイトル → URL セーフな slug。

    日本語をそのまま使うと URL でエンコードされて見栄え悪いので、
    タイトルのハッシュ + 日付プレフィクスで一意化する。
    """
    # 英数字とハイフンだけを残す
    norm = unicodedata.normalize("NFKC", title)
    ascii_part = re.sub(r"[^a-zA-Z0-9\-]+", "-", norm)
    ascii_part = re.sub(r"-+", "-", ascii_part).strip("-").lower()
    if len(ascii_part) > 40:
        ascii_part = ascii_part[:40].rstrip("-")

    # 日本語タイトルから ascii が取れない場合は完全にハッシュ
    if len(ascii_part) < 4:
        h = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
        return f"{date_str}-{h}"
    h = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
    return f"{date_str}-{ascii_part}-{h}"


# ---------------------------------------------------------------------------
# Frontmatter formatter
# ---------------------------------------------------------------------------
def format_pubdate(dt: datetime) -> str:
    """Astro 既定の `'May 30 2026'` 形式。"""
    return dt.strftime("%b %d %Y")


def escape_yaml_single_quote(s: str) -> str:
    return s.replace("'", "''")


def build_frontmatter(
    title: str,
    description: str,
    pub_dt: datetime,
    category: str,
    hero_image_url: Optional[str] = None,
) -> str:
    title_e = escape_yaml_single_quote(title)
    desc_e = escape_yaml_single_quote(description)
    cat_e = escape_yaml_single_quote(category)
    lines = [
        "---",
        f"title: '{title_e}'",
        f"description: '{desc_e}'",
        f"pubDate: '{format_pubdate(pub_dt)}'",
        f"category: '{cat_e}'",
    ]
    if hero_image_url:
        hero_e = escape_yaml_single_quote(hero_image_url)
        lines.append(f"heroImage: '{hero_e}'")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 新レイアウト: H2 画像 / インラインアフィ / 関連記事
# ---------------------------------------------------------------------------
def extract_h2_titles(body_markdown: str) -> List[str]:
    """本文中の H2 見出しテキストを登場順に返す。

    フェンスドコードブロック（```）内の `## ...` は見出しではないので除外する。
    """
    titles: List[str] = []
    in_fence = False
    for line in body_markdown.splitlines():
        if _is_fence_line(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _H2_RE.match(line)
        if m:
            titles.append(m.group(1).strip())
    return titles


def _is_skip_heading(title: str) -> bool:
    return any(key in title for key in _SKIP_ENRICH_HEADINGS)


@dataclass
class _Section:
    heading: str          # 見出し行そのもの（"## xxx"）。preamble は ""
    title: str            # 見出しテキスト。preamble は ""
    lines: List[str]      # 見出しを除く本文行


def _split_sections(body_markdown: str) -> List[_Section]:
    """本文を preamble + 各 H2 セクションに分割する。"""
    sections: List[_Section] = []
    current = _Section(heading="", title="", lines=[])
    in_fence = False
    for line in body_markdown.splitlines():
        if _is_fence_line(line):
            in_fence = not in_fence
            current.lines.append(line)
            continue
        m = None if in_fence else _H2_RE.match(line)
        if m:
            sections.append(current)
            current = _Section(heading=line, title=m.group(1).strip(), lines=[])
        else:
            current.lines.append(line)
    sections.append(current)
    return sections


def insert_h2_enrichments(
    body_markdown: str,
    h2_image_map: Optional[Dict[int, str]] = None,
    inline_affiliates: Optional[List[Dict]] = None,
) -> str:
    """各 H2 セクションに画像とインラインアフィを織り込んだ本文を返す。

    - 画像: H2 見出しの直下に `![title](url)` を挿入（h2_image_map のキーは
      1-indexed の H2 位置）
    - インラインアフィ: format_inline_affiliate() が非空を返す案件を、まとめ/
      参考等を除いた本文セクション末尾に最大 len(inline_affiliates) 個まで分散
      挿入（1 セクション 1 個まで、押し付けない）

    h2_image_map / inline_affiliates が両方空なら body をそのまま返す（後方互換）。
    """
    h2_image_map = h2_image_map or {}
    inline_affiliates = inline_affiliates or []

    # 出力する（承認済み）アフィ文字列だけ先に確定
    aff_strings = [s for s in (format_inline_affiliate(i) for i in inline_affiliates) if s]

    if not h2_image_map and not aff_strings:
        return body_markdown

    sections = _split_sections(body_markdown)

    # アフィを差し込める本文セクションの index（preamble と skip 見出しを除外）
    enrich_targets = [
        idx for idx, s in enumerate(sections)
        if s.heading and not _is_skip_heading(s.title)
    ]
    # 最終セクションは締め（まとめ等でなくても）になりがちなので、可能なら避ける
    if len(enrich_targets) > 1:
        enrich_targets = enrich_targets[:-1] or enrich_targets

    # アフィを対象セクションへ均等に割り当て（1 セクション 1 個）
    aff_assignment: Dict[int, str] = {}
    if aff_strings and enrich_targets:
        step = max(1, len(enrich_targets) // len(aff_strings))
        slots = enrich_targets[::step][: len(aff_strings)]
        for slot_idx, aff in zip(slots, aff_strings):
            aff_assignment[slot_idx] = aff

    out: List[str] = []
    h2_counter = 0
    for idx, sec in enumerate(sections):
        if not sec.heading:
            # preamble はそのまま
            out.extend(sec.lines)
            continue
        h2_counter += 1
        out.append(sec.heading)
        # 見出し直下に画像
        img_url = h2_image_map.get(h2_counter)
        if img_url:
            alt = sec.title.replace("]", "").replace("[", "")
            out.append("")
            out.append(f"![{alt}]({img_url})")
        # セクション本文
        body_lines = list(sec.lines)
        aff = aff_assignment.get(idx)
        if aff:
            # 末尾の余分な空行を畳んでからアフィ行を足す
            while body_lines and body_lines[-1].strip() == "":
                body_lines.pop()
            body_lines.append(aff.rstrip("\n"))
        out.extend(body_lines)

    return "\n".join(out)


def build_related_posts_section(related_posts: Optional[List]) -> str:
    """末尾「## 関連記事」セクションの markdown を組み立てる。

    related_posts は title / url / description 属性を持つオブジェクト
    （related_posts.Post）のリスト。空なら "" を返す（セクションを出さない）。
    """
    if not related_posts:
        return ""
    lines = ["## 関連記事", ""]
    for p in related_posts:
        title = getattr(p, "title", "") or ""
        url = getattr(p, "url", "") or ""
        desc = (getattr(p, "description", "") or "").strip()
        if not title or not url:
            continue
        lines.append(f"- [{title}]({url})")
        if desc:
            lines.append(f"  {desc}")
    if len(lines) <= 2:
        return ""
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------
def render_article(
    title: str,
    description: str,
    body_markdown: str,
    category: str,
    subtopic_key: str,
    pub_dt: datetime,
    dry_run_dir: str = "",
    hero_image_url: Optional[str] = None,
    h2_image_map: Optional[Dict[int, str]] = None,
    inline_affiliates: Optional[List[Dict]] = None,
    related_posts: Optional[List] = None,
) -> Tuple[str, str, List[str]]:
    """
    記事ファイルを作成。

    Args:
        hero_image_url: frontmatter に書き込む heroImage の URL/パス。
            None の場合は frontmatter に heroImage 行を入れない。
            通常は `/images/articles/{slug}.{ext}` のような public 配下パス。
        h2_image_map: {1-indexed H2 位置: 公開URL}。各 H2 見出し直下に画像を挿入。
        inline_affiliates: 本文中に挿入するアフィ候補（catalog item dict のリスト）。
            承認済み（approved=true）のものだけが実際に出力される。
        related_posts: 末尾「## 関連記事」用の Post オブジェクトのリスト。

    新レイアウト系 3 引数はすべて任意。None/空なら従来どおりの出力になる
    （既存パイプライン・既存記事との後方互換を保つ）。

    Returns: (filepath, slug, used_affiliate_labels)
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category {category!r}. Must be one of {VALID_CATEGORIES}"
        )
    if not title.strip():
        raise ValueError("Title is empty")
    if not body_markdown.strip():
        raise ValueError("Body markdown is empty")

    # タイトル長制限
    title = title.strip()
    if len(title) > 80:
        LOG.warning("Title too long (%d chars), trimming to 80", len(title))
        title = title[:80].rstrip()
    description = (description or "").strip()
    if len(description) > 160:
        description = description[:160].rstrip()

    # 1. アフィリエイト置換（末尾トークン → 実 HTML）
    body_replaced, used_labels = replace_tokens(body_markdown, category, subtopic_key)

    # 1.2 新レイアウト: H2 画像 + 本文中インラインアフィを織り込む
    body_enriched = insert_h2_enrichments(
        body_replaced, h2_image_map, inline_affiliates
    )

    # 1.3 末尾「## 関連記事」セクションを付与
    related_section = build_related_posts_section(related_posts)
    if related_section:
        body_enriched = body_enriched.rstrip() + "\n\n" + related_section

    # 2. PR 表記を冒頭に強制挿入
    body_final = prepend_pr_notice(body_enriched)

    # 3. frontmatter + 本文を結合
    fm = build_frontmatter(title, description, pub_dt, category, hero_image_url)
    full_md = fm + "\n" + body_final.strip() + "\n"

    # 4. slug + filepath
    date_str = pub_dt.strftime("%Y-%m-%d")
    slug = slugify(title, date_str)
    out_dir = dry_run_dir or BLOG_DIR
    os.makedirs(out_dir, exist_ok=True)
    filepath = os.path.join(out_dir, f"{slug}.md")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_md)

    LOG.info("Wrote article: %s (%d chars body, %d affiliates: %s, hero=%s)",
             filepath, len(body_final), len(used_labels), used_labels,
             hero_image_url or "(none)")
    return filepath, slug, used_labels
