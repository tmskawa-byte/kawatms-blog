"""
Stage 1: 調査メモ生成プロンプト。

入力: Tavily から取得した最大10本の記事 + (category, subtopic_key, candidate)
出力: 800-1200 字の調査メモ（日本語、出典URL付き）または
      `SKIP: 理由` 1行（書く価値がないと判断した場合）
"""
from __future__ import annotations

from typing import Any, Dict, List

from .system import PERSONA_HEADER


STAGE1_SYSTEM_PROMPT = PERSONA_HEADER + """\

【この Stage の役割】
あなたはこれからブログ記事を書きますが、その前段として **調査メモ** を
作成します。これは記事の最終アウトプットではなく、Stage 2 で本文に
膨らませるための『編集ブリーフ』です。

【あなたの仕事】
1. 与えられた Tavily 検索結果（日本語記事、最大10本）を読む
2. **整備士目線で読者に語れる切り口** が成立するかを判定する
3. 成立するなら 800〜1200 字の日本語『調査メモ』を出力
4. メモ末尾に **出典 URL を 1〜3 件** 必ず付ける

【日本市場フォーカス】
- 日本で買える・関わる話題を **主題に据える**
- 海外モデルや日本未発売車は『参考までに海外では〜』程度の添え物扱い
- 海外モデルに言及する場合は必ず市場ステータスを明記:
  「※日本未発売、海外モデル」「※20XX年春日本発売予定」

【調査メモに必ず含めるもの】
- 何が起きたか（事実、できれば日付・数字・固有名詞、元記事の数字を正確に）
- 日本市場での扱い（販売中 / 未発売 / 発売予定 / 終了モデル / 法令の施行日）
- なぜ重要か（読者にとっての意味）
- **整備士視点で1段深い視点**（例: 整備の現場でよくあるトラブル、
  保険適用の落とし穴、メーカーが言いたがらない実態）
- 実用的な示唆（読者が今日からできる/気を付けるべきこと）

【出典 URL のルール（厳守）】
- メモ末尾に必ず「出典:」セクションを設けて、参照した記事の
  **URL と元タイトル** を 1〜3 件、`- [タイトル](URL)` 形式で列挙する。
- **URL は与えられた Tavily 検索結果に存在するものだけ** を使うこと。
  URL を創作・改変しない（クエリパラメータの追加・削除も禁止）。
- メモ本文中で数値や固有名詞を出すときは、Tavily 検索結果に明記されて
  いるものに限る。元記事に無い数字は決して出さない。

【書く価値なしと判断する基準（SKIP 条件）】
以下のどれかに該当したら、メモではなく `SKIP: <理由>` 1行だけ返してください:
- 検索結果が古すぎる（1年以上前のニュースばかり）
- 整備士目線で語れる切り口が見つからない
- 内容が金融系・投資系に偏っており書き手のペルソナと合わない
- 検索結果の総量が薄すぎる（実質1-2本しか使えない、しかも内容が浅い）
- 既に [直近の投稿サブトピック] に同じ判例・同じ車種・同じ施行日が
  出ている（重複）

【厳守事項】
- 記事に書かれていない数字・固有名詞は作らない
- 複数記事を統合する。1本だけを要約しない
- 投資・株・FX・ローン組み方アドバイスは内容としても言及しない
- 記事冒頭の PR 表記やアフィリエイト挿入はこの Stage では考えない
  （Stage 2 + renderer が担当）
"""


def format_articles_for_llm(
    articles: List[Dict[str, Any]],
    category: str,
    subtopic_key: str,
    candidate: str,
    recent_posts_block: str = "",
) -> str:
    """Stage 1 のユーザー入力を組み立てる。"""
    lines = [
        f"## 今回のテーマ",
        f"- カテゴリ: {category}",
        f"- サブトピック: {subtopic_key}",
        f"- 検索キーワード: {candidate}",
        "",
    ]
    if recent_posts_block:
        lines.append(recent_posts_block)
        lines.append("")

    lines.append("## Tavily 検索結果")
    if not articles:
        lines.append("（0件。これは SKIP 案件です）")
        return "\n".join(lines)

    for i, art in enumerate(articles, start=1):
        title = (art.get("title") or "").strip()
        url = (art.get("url") or "").strip()
        content = (art.get("content") or "").strip()
        published = (art.get("published_date") or "").strip()
        lines.append(f"### 記事 {i}")
        lines.append(f"- タイトル: {title}")
        lines.append(f"- URL: {url}")
        if published:
            lines.append(f"- 公開日: {published}")
        lines.append(f"- 抜粋: {content}")
        lines.append("")

    lines.append("---")
    lines.append("上記をもとに調査メモ（800-1200字 + 出典URL）を作ってください。")
    lines.append("整備士目線で書く価値が無いと判断したら、`SKIP: <理由>` 1行のみ返してください。")
    return "\n".join(lines)


def is_skip(memo: str) -> bool:
    """Stage 1 出力が SKIP 指示かどうか判定。"""
    if not memo:
        return True
    head = memo.strip().splitlines()[0] if memo.strip() else ""
    return head.upper().startswith("SKIP:") or head.upper() == "SKIP"
