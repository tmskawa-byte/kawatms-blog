"""
カテゴリ別 A8 案件マッピング + プレースホルダ置換ロジック。

A8 の素材 HTML / リンクは config/affiliates.json で管理（承認前は空欄でOK）。
本ファイルは「どの記事に何の広告を出すか」の対応関係と、Stage 2 が
本文に埋めるプレースホルダトークンを実 HTML に置換する処理を持つ。
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

LOG = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "affiliates.json")
CATALOG_PATH = os.path.join(REPO_ROOT, "config", "affiliate_catalog.yaml")

# ---------------------------------------------------------------------------
# カテゴリ × サブトピック → 推奨 A8 案件キーのリスト
# affiliate_strategy_a8net.md の Part 4 を参考に作成
# ---------------------------------------------------------------------------
# Emptied during A8 media review phase. Reintroduce after approval.
AFFILIATE_MAP: Dict[Tuple[str, str], List[str]] = {}


# プレースホルダトークンの正規表現
TOKEN_RE = re.compile(r"<!--\s*AFF:(CARD_\d+|INLINE_\d+)\s*-->")

# PR表記（記事冒頭に必ず挿入される文言）
PR_NOTICE = "> ※本記事にはアフィリエイト広告（プロモーション）が含まれます。"

# ---------------------------------------------------------------------------
# 楽天市場 末尾誘導フッター (Phase A)
# ---------------------------------------------------------------------------
# A8 経由の楽天市場 top リンク。a8mat / a26060120254 はメディア固有の値で、
# 案件変更時はここだけ書き換える。
RAKUTEN_AFFILIATE_URL = (
    "https://rpx.a8.net/svt/ejp?"
    "a8mat=4B5LK1+3GFM7M+2HOM+686ZL"
    "&rakuten=y"
    "&a8ejpredirect=http%3A%2F%2Fhb.afl.rakuten.co.jp%2Fhgc%2F"
    "0ea62065.34400275.0ea62066.204f04c0%2F"
    "a26060120254_4B5LK1_3GFM7M_2HOM_686ZL"
    "%3Fpc%3Dhttp%253A%252F%252Fwww.rakuten.co.jp%252F"
    "%26m%3Dhttp%253A%252F%252Fm.rakuten.co.jp%252F"
)

# 末尾セクション (Markdown)。
# - 見出しは `## 🛒 整備用品をチェック`
# - リンクは `<a rel="sponsored nofollow" target="_blank">` の生 HTML を使う
#   (Astro は `.md` でも remark+rehype 経由で raw HTML を許可するため安全)
# - 景品表示法のステマ規制対応として「アフィリエイト広告」を明示
RAKUTEN_FOOTER_MD = (
    "## 🛒 整備用品をチェック\n"
    "\n"
    "記事で紹介した工具・ケミカルの実物は楽天市場でチェックできます。\n"
    "\n"
    f'👉 <a href="{RAKUTEN_AFFILIATE_URL}" '
    'rel="sponsored nofollow" target="_blank">楽天市場で整備用品を見る</a>\n'
    "\n"
    "※ アフィリエイト広告：購入により当ブログに紹介料が発生する場合があります。\n"
)


def append_rakuten_footer(body_markdown: str) -> str:
    """記事末尾に楽天市場誘導フッターを付与。

    既に同セクション（`rpx.a8.net` を含む or 見出し文言）が含まれていたら
    二重挿入を避けてそのまま返す。Stage 2 の生成物に対しても安全。
    """
    if "rpx.a8.net" in body_markdown:
        return body_markdown
    if "整備用品をチェック" in body_markdown:
        return body_markdown
    return body_markdown.rstrip() + "\n\n" + RAKUTEN_FOOTER_MD




# ---------------------------------------------------------------------------
# Config IO
# ---------------------------------------------------------------------------
def load_affiliate_config() -> Dict[str, Dict]:
    """config/affiliates.json を読み込む。

    フォーマット:
        {
          "<key>": {
            "label": "...",
            "card_html": "...",        # AFF:CARD_N 用
            "inline_html": "...",      # AFF:INLINE_N 用（任意）
            "approved": true|false
          },
          ...
        }
    """
    if not os.path.exists(CONFIG_PATH):
        LOG.warning("affiliates.json not found at %s; using empty config", CONFIG_PATH)
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        LOG.warning("affiliates.json unreadable (%s); using empty config", e)
        return {}


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def select_affiliates(
    category: str,
    subtopic_key: str,
    max_count: int = 2,
) -> List[str]:
    """カテゴリ×サブトピック → 採用キーのリスト。"""
    key = (category, subtopic_key)
    if key not in AFFILIATE_MAP:
        # アドホック系のフォールバック
        key = (category, "_default")
    candidates = AFFILIATE_MAP.get(key, [])
    return candidates[:max_count]


def build_affiliate_hint(category: str, subtopic_key: str) -> str:
    """Stage 2 プロンプトに渡す『どの広告を埋めるか』ヒント。"""
    cfg = load_affiliate_config()
    keys = select_affiliates(category, subtopic_key)
    if not keys:
        return "（このカテゴリにマッチする広告がないため、トークン埋め込みは任意）"

    lines = ["本文中盤に次のトークンを挿入してください（renderer が実広告に置換します）:"]
    for i, k in enumerate(keys, start=1):
        item = cfg.get(k, {})
        label = item.get("label", k)
        lines.append(f"- `<!-- AFF:CARD_{i} -->` … {label} を想定")
    lines.append(
        "段落と段落の間に独立した行として置く。本文の途中に埋め込まない。"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Replacement
# ---------------------------------------------------------------------------
def replace_tokens(
    body_markdown: str,
    category: str,
    subtopic_key: str,
) -> Tuple[str, List[str]]:
    """body_markdown 内の AFF プレースホルダを実 HTML/markdown に置換。

    Returns: (置換後の本文, 採用された広告ラベルのリスト)
    """
    cfg = load_affiliate_config()
    keys = select_affiliates(category, subtopic_key)
    used_labels: List[str] = []

    # CARD_1 → keys[0], CARD_2 → keys[1] の順で対応
    def card_for(idx: int) -> Optional[Tuple[str, str]]:
        """1-indexed CARD_idx に対応する (label, html) を返す。"""
        if idx - 1 >= len(keys):
            return None
        k = keys[idx - 1]
        item = cfg.get(k, {})
        if not item.get("approved", False):
            return (item.get("label", k), "")  # 未承認は空文字置換 → トークン消滅
        return (
            item.get("label", k),
            item.get("card_html") or item.get("inline_html") or "",
        )

    def repl(match: re.Match) -> str:
        token = match.group(1)
        kind, idx_str = token.split("_")
        try:
            idx = int(idx_str)
        except ValueError:
            return ""
        chosen = card_for(idx)
        if chosen is None:
            return ""  # トークンの番号が広告数を超えていた → 黙って消す
        label, html = chosen
        used_labels.append(label)
        if not html:
            # 未承認 placeholder: HTML コメントとして残す（後で気付けるよう）
            return f"<!-- {label} (未承認のため空欄) -->"
        return html

    replaced = TOKEN_RE.sub(repl, body_markdown)

    # トークンが本文に1つも無かった場合、末尾に「## 関連サービス」セクションを自動追加
    if not used_labels and keys:
        related_block = _build_related_section(cfg, keys)
        if related_block:
            replaced = replaced.rstrip() + "\n\n" + related_block + "\n"
            used_labels.extend(
                cfg.get(k, {}).get("label", k) for k in keys
            )

    return replaced, used_labels


def _build_related_section(cfg: Dict[str, Dict], keys: List[str]) -> str:
    """末尾用『## 関連サービス』セクションを組み立てる。"""
    blocks = []
    for k in keys:
        item = cfg.get(k, {})
        label = item.get("label", k)
        html = item.get("card_html") or item.get("inline_html") or ""
        if item.get("approved", False) and html:
            blocks.append(html)
        else:
            blocks.append(f"<!-- {label} (未承認のため空欄) -->")
    if not blocks:
        return ""
    return "## 関連サービス\n\n" + "\n\n".join(blocks)


def prepend_pr_notice(body_markdown: str) -> str:
    """記事冒頭にステマ規制対応の PR 表記を必ず付与。

    既に存在していたら（AIが書いてしまった等）二重挿入を避ける。
    """
    head = body_markdown.lstrip().splitlines()[:3]
    head_text = "\n".join(head)
    if "アフィリエイト" in head_text and ("プロモーション" in head_text or "PR" in head_text):
        return body_markdown
    return PR_NOTICE + "\n\n" + body_markdown.lstrip()


# ===========================================================================
# 本文中インラインアフィリエイト（config/affiliate_catalog.yaml）
# ===========================================================================
# HANDOFF: 記事本文の H2 セクション内に関連商品リンクを 1〜2 個、自然に挿入する。
# 既存の末尾 AFF トークン / 楽天フッターとは独立した経路。
#
# 制約（絶対遵守）: 保険・金融・投資・FX・暗号資産・自動車保険一括見積もり、
# 楽天損保 / 楽天証券 / 楽天カード等の金融系は出さない。カタログ側でも除外して
# いるが、ここでも denylist で二重チェックし、混入を物理的に防ぐ。

# 禁止語（title / tags / categories / url / affiliate を結合した文字列に対して
# 部分一致で判定）。誤検出を避けるため意味が一意に金融・保険に寄る語に限定。
INLINE_AFFILIATE_DENYLIST: Tuple[str, ...] = (
    "保険",
    "生命保険",
    "自動車保険",
    "損保",
    "一括見積",
    "投資",
    "投信",
    "証券",
    "fx",
    "暗号資産",
    "仮想通貨",
    "カードローン",
    "クレジットカード",
    "キャッシング",
    "ローン",
    "金融",
    "銀行",
    "bot",
    "楽天カード",
    "楽天証券",
    "楽天損保",
    "楽天銀行",
)

# インライン挿入フォーマット。景表法対応で rel="sponsored nofollow" を付ける。
_INLINE_FMT = (
    '\n\n💡 こちらもどうぞ：'
    '<a href="{url}" rel="sponsored nofollow" target="_blank">{title}</a>\n'
)


def _catalog_text_blob(item: Dict[str, Any]) -> str:
    """compliance 判定用に item のテキスト要素を 1 本に結合（小文字化）。"""
    parts: List[str] = [
        str(item.get("title", "")),
        str(item.get("url", "")),
        str(item.get("affiliate", "")),
    ]
    parts.extend(str(t) for t in (item.get("tags") or []))
    parts.extend(str(c) for c in (item.get("categories") or []))
    return " ".join(parts).lower()


def is_compliant_affiliate(item: Dict[str, Any]) -> bool:
    """禁止語を 1 つでも含む案件は不採用（保険・金融・投資系の混入防止）。"""
    blob = _catalog_text_blob(item)
    for bad in INLINE_AFFILIATE_DENYLIST:
        if bad in blob:
            LOG.warning(
                "Inline affiliate rejected by denylist (%r): %s",
                bad, item.get("title", "(no title)"),
            )
            return False
    return True


def load_affiliate_catalog(path: str = CATALOG_PATH) -> List[Dict[str, Any]]:
    """affiliate_catalog.yaml を読み込み、制約準拠の案件だけ返す。

    PyYAML は遅延 import。未インストール / 読み込み失敗時は空リストにフォール
    バックし、インラインアフィ機能だけを無効化する（パイプライン全体は止めない）。
    """
    if not os.path.exists(path):
        LOG.warning("affiliate_catalog.yaml not found at %s; inline affiliates disabled", path)
        return []
    try:
        import yaml  # 遅延 import: 未導入でも他機能を巻き込まない
    except ImportError:
        LOG.warning("PyYAML not available; inline affiliates disabled")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, Exception) as e:  # yaml.YAMLError 含む
        LOG.warning("affiliate_catalog.yaml unreadable (%s); inline affiliates disabled", e)
        return []
    if not isinstance(data, list):
        LOG.warning("affiliate_catalog.yaml is not a list; ignoring")
        return []
    items = [it for it in data if isinstance(it, dict) and it.get("title") and it.get("url")]
    return [it for it in items if is_compliant_affiliate(it)]


def select_inline_affiliates(
    category: str,
    tags: Sequence[str],
    max_count: int = 2,
    *,
    catalog: Optional[List[Dict[str, Any]]] = None,
    rng: Optional[random.Random] = None,
) -> List[Dict[str, Any]]:
    """カテゴリ・タグマッチで本文中アフィ候補を最大 max_count 件選定。

    approved による絞り込みはしない（dry-run で候補表示できるように）。実際に
    リンクを出すかは format_inline_affiliate() が approved で判断する。
    """
    pool = catalog if catalog is not None else load_affiliate_catalog()
    tagset = set(tags or [])

    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    for idx, item in enumerate(pool):
        cats = item.get("categories") or []
        if category not in cats:
            continue
        overlap = len(set(item.get("tags") or []) & tagset)
        # カテゴリ一致は前提。タグ重複が多いほど優先。重複 0 でも候補には残す。
        scored.append((overlap, idx, item))

    # タグ重複降順 → カタログ出現順で安定ソート
    scored.sort(key=lambda t: (-t[0], t[1]))
    selected = [item for _, _, item in scored[:max_count]]

    # rng が与えられていれば同点群をシャッフルせず順序維持（決定論性優先）。
    # 押し付けないため最大 max_count（HANDOFF: 1 記事 2 個まで）で打ち切り。
    if rng is not None and len(scored) > max_count:
        # 上位 max_count はそのまま。決定論テスト用に rng は予約のみ。
        pass
    return selected


def format_inline_affiliate(item: Dict[str, Any]) -> str:
    """本文中 H2 末尾に差し込む 1 行を返す。

    未承認（approved=false）/ 非準拠 / url 欠落 のときは空文字を返し、render
    側で挿入をスキップさせる（偽リンク・未承認リンクを公開しない）。
    """
    if not item.get("approved", False):
        return ""
    if not is_compliant_affiliate(item):
        return ""
    url = str(item.get("url", "")).strip()
    title = str(item.get("title", "")).strip()
    if not url or not title:
        return ""
    return _INLINE_FMT.format(url=url, title=title)
