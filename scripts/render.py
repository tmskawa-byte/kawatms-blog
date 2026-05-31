"""
記事 JSON → src/content/blog/{YYYY-MM-DD}-{slug}.md ファイル化。

- frontmatter: title, description, pubDate (Astro 形式の 'May 30 2026'), category
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
from datetime import datetime
from typing import Dict, List, Tuple

from scripts.affiliates import prepend_pr_notice, replace_tokens

LOG = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOG_DIR = os.path.join(REPO_ROOT, "src", "content", "blog")

VALID_CATEGORIES = {"整備の現場", "越境EC事業", "AI・自動化", "対馬ライフ"}


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
) -> str:
    title_e = escape_yaml_single_quote(title)
    desc_e = escape_yaml_single_quote(description)
    cat_e = escape_yaml_single_quote(category)
    return (
        "---\n"
        f"title: '{title_e}'\n"
        f"description: '{desc_e}'\n"
        f"pubDate: '{format_pubdate(pub_dt)}'\n"
        f"category: '{cat_e}'\n"
        "---\n"
    )


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
) -> Tuple[str, str, List[str]]:
    """
    記事ファイルを作成。

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

    # 1. アフィリエイト置換
    body_replaced, used_labels = replace_tokens(body_markdown, category, subtopic_key)

    # 2. PR 表記を冒頭に強制挿入
    body_final = prepend_pr_notice(body_replaced)

    # 3. frontmatter + 本文を結合
    fm = build_frontmatter(title, description, pub_dt, category)
    full_md = fm + "\n" + body_final.strip() + "\n"

    # 4. slug + filepath
    date_str = pub_dt.strftime("%Y-%m-%d")
    slug = slugify(title, date_str)
    out_dir = dry_run_dir or BLOG_DIR
    os.makedirs(out_dir, exist_ok=True)
    filepath = os.path.join(out_dir, f"{slug}.md")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_md)

    LOG.info("Wrote article: %s (%d chars body, %d affiliates: %s)",
             filepath, len(body_final), len(used_labels), used_labels)
    return filepath, slug, used_labels
