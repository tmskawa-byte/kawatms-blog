# GitHub Actions Secrets 設定

`Settings → Secrets and variables → Actions → New repository secret` で 2 つ登録。

## 必須

| Secret 名 | 用途 | 取得元 |
|---|---|---|
| `CHATLLM_API_KEY` | 記事生成（Gemini 3.1 Pro Preview via RouteLLM） | Abacus.AI ChatLLM 管理画面 |
| `TAVILY_API_KEY` | 一次情報の Web 検索 | https://tavily.com 管理画面 |

`ig-autopost` で既に登録済みなら **同じキーをそのまま再登録** すれば OK（共有はできないので、同じ値を kawatms-blog 側にも入れる）。

## 不要

- `GITHUB_TOKEN` は Actions が自動付与するため設定不要
- A8 の素材コードは **Secrets ではなく** `config/affiliates.json` に同梱
  - 公開リンクなので Secrets 化する必要なし
  - 承認前は空欄のまま運用可（記事内に `<!-- 案件名 (未承認のため空欄) -->` というコメントが残るだけ）

## 動作確認

1. Secrets 登録後、`Actions → Auto Article → Run workflow` を開く
2. `dry_run: true`、`preview_only: false`、`category: 整備の現場`、`subtopic: 整備情報` を選択
3. 実行 → ログで以下を確認:
   - Tavily が記事を返している
   - Stage 1 メモが SKIP していない
   - Stage 2 で title / body が生成されている
   - `src/content/blog/{slug}.md` が作られている
   - PR は **作られない**（dry_run=true のため）
4. 問題なければ `dry_run: false` で再実行 → PR が出る → 中身を確認してマージ

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `CHATLLM_API_KEY is not set` | Secret 未登録 | 上記参照 |
| `TAVILY_API_KEY is not set` | 同上 | |
| Stage 1 SKIP 連発 | 検索ドメイン or キーワードと相性悪い | `scripts/topics.py` の `*_DOMAINS` や `extra_query` を見直し |
| Stage 2 JSON parse 失敗 | LLM が文章で返している | プロンプトの JSON 強制部を強める、または再実行 |
| 同じサブトピックが続く | 直近5件除外で全部除外され fallback 発火 | `SUBTOPIC_EXCLUDE_WINDOW` を 3 に下げる |
| PR が作られない | dry_run=true で実行している | `dry_run: false` で再実行 |
