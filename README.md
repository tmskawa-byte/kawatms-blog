# Astro Starter Kit: Blog

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/cloudflare/templates/tree/main/astro-blog-starter-template)

![Astro Template Preview](https://github.com/withastro/astro/assets/2244813/ff10799f-a816-4703-b967-c78997e8323d)

<!-- dash-content-start -->

Create a blog with Astro and deploy it on Cloudflare Workers as a [static website](https://developers.cloudflare.com/workers/static-assets/).

Features:

- ✅ Minimal styling (make it your own!)
- ✅ 100/100 Lighthouse performance
- ✅ SEO-friendly with canonical URLs and OpenGraph data
- ✅ Sitemap support
- ✅ RSS Feed support
- ✅ Markdown & MDX support
- ✅ Built-in Observability logging

<!-- dash-content-end -->

## Getting Started

Outside of this repo, you can start a new project with this template using [C3](https://developers.cloudflare.com/pages/get-started/c3/) (the `create-cloudflare` CLI):

```bash
npm create cloudflare@latest -- --template=cloudflare/templates/astro-blog-starter-template
```

A live public deployment of this template is available at [https://astro-blog-starter-template.templates.workers.dev](https://astro-blog-starter-template.templates.workers.dev)

## 🚀 Project Structure

Astro looks for `.astro` or `.md` files in the `src/pages/` directory. Each page is exposed as a route based on its file name.

There's nothing special about `src/components/`, but that's where we like to put any Astro/React/Vue/Svelte/Preact components.

The `src/content/` directory contains "collections" of related Markdown and MDX documents. Use `getCollection()` to retrieve posts from `src/content/blog/`, and type-check your frontmatter using an optional schema. See [Astro's Content Collections docs](https://docs.astro.build/en/guides/content-collections/) to learn more.

Any static assets, like images, can be placed in the `public/` directory.

## 🧞 Commands

All commands are run from the root of the project, from a terminal:

| Command                           | Action                                           |
| :-------------------------------- | :----------------------------------------------- |
| `npm install`                     | Installs dependencies                            |
| `npm run dev`                     | Starts local dev server at `localhost:4321`      |
| `npm run build`                   | Build your production site to `./dist/`          |
| `npm run preview`                 | Preview your build locally, before deploying     |
| `npm run astro ...`               | Run CLI commands like `astro add`, `astro check` |
| `npm run astro -- --help`         | Get help using the Astro CLI                     |
| `npm run build && npm run deploy` | Deploy your production site to Cloudflare        |
| `npm wrangler tail`               | View real-time logs for all Workers              |

## 👀 Want to learn more?

Check out [our documentation](https://docs.astro.build) or jump into our [Discord server](https://astro.build/chat).

## Credit

This theme is based off of the lovely [Bear Blog](https://github.com/HermanMartinus/bearblog/).

---

## 🤖 自動記事生成パイプライン

このリポは **AI が週4回ブログ記事を自動生成 → PR を起こす** パイプラインを内蔵しています（`feature/auto-article-pipeline` で導入）。

### スケジュール（JST）

| 曜日 | カテゴリ | サブテーマ |
|---|---|---|
| 月 7:00 | 整備の現場 | 新車情報 |
| 水 7:00 | 整備の現場 | 整備情報 |
| 金 7:00 | 整備の現場 | 道路交通法 → 新技術新TEC → 保険（ローテ） |
| 日 7:00 | アドホック | 越境EC事業 → AI・自動化 → 対馬ライフ（ローテ） |

→ 月 ~16本 / Cloudflare Pages に自動デプロイ。

### パイプライン

```
GitHub Actions (cron)
  → Tavily で一次情報検索
  → Stage 1: 調査メモ生成 (Gemini 3.1 Pro Preview)
     SKIP 判定なら静かに終了
  → Stage 2: 記事本文 + メタ JSON 生成
  → アフィリエイト自動挿入 + PR 表記付与
  → src/content/blog/{slug}.md 作成
  → PR 作成 (label: auto-article)
  → ケンちゃんが GitHub Mobile で確認 → Merge
  → Cloudflare 自動デプロイ
  → state_update.yml が rotation を進める
```

### ファイル構成

```
scripts/
  generate_article.py    # メインエントリ
  bump_state.py          # PR マージ後の state 更新
  render.py              # markdown ファイル化
  affiliates.py          # A8 案件マッピング + プレースホルダ置換
  topics.py              # カテゴリ/サブトピック定義 + 曜日ロジック
  lib/
    chatllm_client.py    # RouteLLM API
    tavily_client.py     # Tavily Search API
prompts/
  system.py              # 整備士ペルソナ・文体・禁止事項
  stage1_research.py     # 調査メモプロンプト
  stage2_article.py      # 記事本文プロンプト
  templates.py           # サブトピック別の追加ヒント
state/
  rotation_index.json    # 金曜・日曜ローテ index
  recent_subtopics.json  # 直近20件の履歴（dedup 用）
config/
  affiliates.json        # A8 素材コード（承認後に埋める）
.github/workflows/
  auto_article.yml       # cron + 手動 + PR open
  state_update.yml       # PR merge 後の state 更新
SETUP_SECRETS.md         # Secrets 設定ガイド
```

### Secrets

詳細は [SETUP_SECRETS.md](SETUP_SECRETS.md)。

- `CHATLLM_API_KEY`
- `TAVILY_API_KEY`

### 手動 run

`Actions → Auto Article → Run workflow`:
- `dry_run: true` でテスト（PR は作られない）
- `category` / `subtopic` / `candidate` 入力で強制（曜日ロジック bypass）
- `preview_only: true` でトピック決定だけ表示

### ローカル dry-run

```bash
export CHATLLM_API_KEY="..."
export TAVILY_API_KEY="..."
python scripts/generate_article.py --dry-run \
  --category 整備の現場 --subtopic 整備情報 \
  --out-dir /tmp/test_output
# → /tmp/test_output/{slug}.md が生成される
```

### A8 アフィリエイト

- 提携承認が下りるまで `config/affiliates.json` は `approved: false` のままで OK
- 記事には `<!-- 案件名 (未承認のため空欄) -->` というコメントが残る
- 承認後、該当案件の `card_html` / `inline_html` を埋めて `approved: true` に変更すれば、次の記事から自動で広告が入る

### 既知の運用ポイント

- **rotation_index は PR マージ後に進む**: PR が rejection で閉じられた場合は次回も同じトピックが抽選対象に戻る
- **金融系トピック禁止**: 投資・株・FX・ローン組み方アドバイスはプロンプトレベルでブロック（保険は OK だが整備士目線必須）
- **ハルシネーション抑制**: 数値・固有名詞は Tavily 一次情報の範囲でのみ言及（プロンプトで明示）
- **ステマ規制対応**: 全記事冒頭に「※本記事にはアフィリエイト広告（プロモーション）が含まれます。」を `render.py` が強制挿入

### Blog Patrol → Codex 自動修正

Claude patrol が記事レビューでNGを見つけた場合、対象記事1本だけを別worktreeでCodexに修正させ、build/check後に `patrol-auto-fix` ラベル付きPRを作成できます。初期状態では自動マージは無効です。運用・停止条件・有効化手順は [docs/PATROL_CODEX_AUTO_FIX.md](docs/PATROL_CODEX_AUTO_FIX.md) を参照してください。
