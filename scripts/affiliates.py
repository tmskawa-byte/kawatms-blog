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
from typing import Dict, List, Optional, Tuple

LOG = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "affiliates.json")

# ---------------------------------------------------------------------------
# カテゴリ × サブトピック → 推奨 A8 案件キーのリスト
# affiliate_strategy_a8net.md の Part 4 を参考に作成
# ---------------------------------------------------------------------------
AFFILIATE_MAP: Dict[Tuple[str, str], List[str]] = {
    ("整備の現場", "新車情報"): ["carsensor_kaitori", "gulliver"],
    ("整備の現場", "整備情報"): ["amazon_tools", "rakuten_tools"],
    ("整備の現場", "道路交通法"): ["menkyo_wakaba"],
    ("整備の現場", "新技術新TEC情報"): ["carsensor_kaitori", "gulliver"],
    ("整備の現場", "保険"): ["hoken_square_bang", "insweb"],
    ("越境EC事業", "_default"): ["base_shop"],
    ("AI・自動化", "_default"): ["conoha_wing", "xserver"],
    ("対馬ライフ", "_default"): ["rakuten_travel", "jalan"],
}

# プレースホルダトークンの正規表現
TOKEN_RE = re.compile(r"<!--\s*AFF:(CARD_\d+|INLINE_\d+)\s*-->")

# PR表記（記事冒頭に必ず挿入される文言）
PR_NOTICE = "> ※本記事にはアフィリエイト広告（プロモーション）が含まれます。"


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
