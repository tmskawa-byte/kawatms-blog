"""
Stage 2: 記事本文生成プロンプト。

入力: Stage 1 の調査メモ + カテゴリメタ + 直近サブトピック履歴 + アフィリエイト挿入指示
出力: 厳密 JSON
    {
      "title": "...",
      "description": "...",
      "body_markdown": "## ...\\n\\n...",
      "tags": ["..."]
    }

body_markdown 内に `<!-- AFF:CARD_1 -->` `<!-- AFF:CARD_2 -->` などの
プレースホルダトークンを 1-2 個埋め込む（affiliates.py が実 HTML に置換）。
記事冒頭の PR 表記は render.py が **テンプレで強制挿入** するため
ここでは書かない。
"""
from __future__ import annotations

from typing import List

from .system import PERSONA_HEADER


STAGE2_SYSTEM_PROMPT = PERSONA_HEADER + """\

【この Stage の役割】
Stage 1 で作った調査メモをもとに、ブログ記事1本（1500〜3000字）の
本文 markdown を作成します。

【出力形式（厳密JSON、これ以外の文字を含めない）】
{
  "title": "60字以内の魅力的なタイトル",
  "description": "120字以内のメタ description（記事概要）",
  "body_markdown": "## ... \\n\\n本文（1500〜3000字）",
  "tags": ["タグ1", "タグ2", "タグ3"]
}

【title の作り方】
- 60 字以内（はみ出したら切り詰め）
- 釣りタイトル禁止。「衝撃」「絶対」「保存版」「99%」みたいな煽りは使わない
- 整備士が落ち着いて書いてる感を出す
- 例: 「2026年の自動車保険、車検タイミングで見直すべき3つの理由」

【description の作り方】
- 120 字以内
- 記事の中身を端的に説明。CTAは不要

【body_markdown の構造】
- 見出しは `## ...`（h2）を中心に、必要なら `### ...`（h3）も使う
- 冒頭 100-150 字で「この記事で書くこと」を簡潔に
- 中盤に **整備士の現場感を入れた1段落**（必須）
  例: 「うちのお客様で〜なケースがありました」
- 必要に応じて箇条書き・テーブル・コードブロックを使う
- 末尾に `## まとめ` セクション（100-200字、結論）
- その後に `## 出典` セクション（Stage 1 メモ末尾の出典 URL をそのまま転記、
  1-3 件、`- [タイトル](URL)` 形式）。URL は **Stage 1 メモに存在するもの
  だけ** を使い、創作・改変しない。

【アフィリエイト挿入トークン】
本文中盤の **自然な位置** に以下のトークンを 1〜2 個 埋め込む:
- `<!-- AFF:CARD_1 -->` : 本文の流れに自然な広告カード位置
- `<!-- AFF:CARD_2 -->` : （任意、より深い段落の後）

トークン挿入位置は段落と段落の **間** に独立した行として書くこと。
本文の段落の途中に埋め込まない。

例:
```
## 車検と保険、同じタイミングで見直す合理性

車検は2年に1度くる節目です。だからこそ...

<!-- AFF:CARD_1 -->

## 整備士目線での保険会社の見分け方

実は、保険会社によって...
```

【字数】
- 1500〜3000字（カテゴリで自然に調整）
- 整備の現場: 2000〜3000字（密度高め）
- AI・自動化: 1800〜2500字
- 対馬ライフ: 1500〜2000字（軽め）

【書き出しで「本記事にはアフィリエイト広告が含まれます」と書かない】
冒頭の PR 表記は renderer が自動で先頭に貼ります。Stage 2 では書かない。

【tags の作り方】
3-6 個。サブトピックを表す日本語タグ。例:
- 整備の現場 × 保険記事: ["自動車保険", "車検", "等級ダウン", "整備士目線"]

【厳禁】
- 出力にコードフェンス（```json ... ```）を付けない、純粋な JSON を返す
- Stage 1 のメモを丸写ししない（リライト・膨らませる）
- 投資・株・FX・ローン組み方アドバイスを含めない
- 「俺」「マジで」「フライング」「ヤバい」「ガチで」「ぶっちゃけ」を使わない
- 海外モデル・日本未発売車をメインに据えない
"""


def build_stage2_user_input(
    research_memo: str,
    category: str,
    subtopic_key: str,
    candidate: str,
    recent_posts_block: str = "",
    affiliate_hint: str = "",
) -> str:
    parts = [
        f"## 今回の記事メタ",
        f"- カテゴリ: {category}",
        f"- サブトピック: {subtopic_key}",
        f"- 検索キーワード: {candidate}",
        "",
    ]
    if recent_posts_block:
        parts.append(recent_posts_block)
        parts.append("")

    if affiliate_hint:
        parts.append("## アフィリエイト挿入指示")
        parts.append(affiliate_hint)
        parts.append("")

    parts.append("## Stage 1 調査メモ")
    parts.append(research_memo)
    parts.append("")
    parts.append("---")
    parts.append(
        "上記メモをもとに記事本文を作り、指定の JSON 形式のみを返してください。"
    )
    return "\n".join(parts)


def format_recent_subtopics_for_prompt(
    history: List[dict],
    window: int = 5,
) -> str:
    """直近 window 件の (category, subtopic, title) を Stage1/2 用にフォーマット。"""
    recent = [
        h for h in history[-window:]
        if isinstance(h, dict) and h.get("subtopic")
    ]
    if not recent:
        return ""
    lines = ["## 直近の投稿（これと内容が被らないこと）"]
    for entry in reversed(recent):
        date_str = entry.get("date", "")
        cat = entry.get("category", "")
        sub = entry.get("subtopic", "")
        title = entry.get("title", "")
        lines.append(f"- {date_str} {cat}/{sub}: {title}")
    lines.append("")
    lines.append(
        "【重要】上記と意味的に重なる内容、同じ車種・同じ判例・同じ施行日を"
        "再掲しない。新しい角度・別の切り口で書くこと。"
    )
    return "\n".join(lines)
