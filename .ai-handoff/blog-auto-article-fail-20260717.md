# Blog Auto Article Failure Handoff 2026-07-17

## 結論

- 対象 run: `Auto Article` / run `29540705474`
- 実行時刻: 2026-07-16 22:51:16 UTC / 2026-07-17 07:51:16 JST
- 状態: `completed / failure`、所要 `1m10s`
- 失敗箇所: `Generate article` step 内の Stage 2 article body JSON parse
- exit code: `6`
- PR #58 判定: **効果未確認**

PR #58 の YAML は 7/17 run に読み込まれていたが、記事生成が Stage 2 で失敗したため、`Create Pull Request`、`Merge generated article`、`Bump rotation state after auto-merge` まで到達していない。

ただし PR #58 の merge commit 自体で `state/rotation_index.json` の `subtopic_seibi` は `0 -> 1` に戻っており、7/17 run は実際に `subtopic_index=1` / `整備情報` を選んだ。よって「初期 state を戻す効果」は確認済みだが、「auto-merge 後に inline bump で `1 -> 2` へ進む効果」は未確認。

## 調査コマンド

```powershell
gh run list --repo tmskawa-byte/kawatms-blog --workflow auto_article.yml --limit 5
gh run view 29540705474 --repo tmskawa-byte/kawatms-blog --log
gh run view 29056371007 --repo tmskawa-byte/kawatms-blog --log
gh pr view 58 --repo tmskawa-byte/kawatms-blog --json number,title,state,mergedAt,mergeCommit,headRefName,baseRefName,url,body
```

直近 run:

```text
completed failure Auto Article main schedule 29540705474 1m10s 2026-07-16T22:51:16Z
completed success Auto Article main schedule 29374316373 2m21s 2026-07-14T22:51:08Z
completed success Auto Article main schedule 29211965546 2m4s 2026-07-12T22:39:59Z
completed failure Auto Article main schedule 29056371007 1m6s 2026-07-09T23:04:36Z
completed success Auto Article main schedule 28904338141 2m12s 2026-07-07T22:54:30Z
```

## 7/17 run のログ要点

Run `29540705474` は checkout 時点で `origin/main = 9ca5a5a1a996909b66ae3acc4397ab95ff004b14`、つまり PR #58 merge commit を使用。

記事生成ログ:

```text
Determined topic: weekday=4, subtopic_index=1, category=整備の現場, subtopic_key=整備情報
Candidate pick: 'タイヤ空気圧 点検'
Tavily: 0 results
Stage 1 returned SKIP on attempt 1/4
Retry candidate: 車検 費用 内訳
Tavily: 10 results
Stage 1 length: 1495
Stage 2 (article body) starting...
Stage 2 raw length: 2333
ERROR generate_article: Stage 2 JSON parse failed: No JSON object found
Process completed with exit code 6.
```

Stage 1 は最終的に成功している。ChatLLM/Gemini 呼び出し自体も応答を返しているため、今回の主因は「クレジット枯渇」や「API キー期限切れ」ではなく、Stage 2 の返却 JSON が壊れていたこと。

raw は `{ "title": ..., "description": ..., "body_markdown": ...` で始まるが、完全な JSON object として閉じていない。`scripts/generate_article.py` の `extract_json()` は先頭 `{` と末尾 `}` を探すため、末尾 brace がない応答で exit code 6 になる。

関連箇所:

- `scripts/generate_article.py:183` `extract_json()`
- `scripts/generate_article.py:543` Stage 2 `response_format="json"`
- `scripts/generate_article.py:554` JSON parse failure log
- `scripts/generate_article.py:555` `return 6`
- `scripts/lib/chatllm_client.py:131` `response_format={"type":"json_object"}`

## PR #58 の効果確認

PR #58:

- URL: https://github.com/tmskawa-byte/kawatms-blog/pull/58
- mergedAt: 2026-07-15T09:00:12Z / 2026-07-15 18:00:12 JST
- merge commit: `9ca5a5a1a996909b66ae3acc4397ab95ff004b14`
- title: `fix: auto article merge 後に rotation_index を直接 bump`

`state/rotation_index.json` の推移:

```text
635f9cd 2026-07-01 13:44:27 +0900 feat: rotate blog subtopics weekly (#48)
9ca5a5a 2026-07-15 18:00:12 +0900 fix: auto article merge 後に rotation_index を直接 bump (#58)
```

PR #58 merge 前:

```json
{
  "friday_seibi": 0,
  "sunday_adhoc": 0,
  "subtopic_seibi": 0
}
```

PR #58 merge 後:

```json
{
  "friday_seibi": 0,
  "sunday_adhoc": 0,
  "subtopic_seibi": 1
}
```

7/17 run では `subtopic_index=1` で `整備情報` が選ばれたので、PR #58 の state reset は効いている。

一方、run は `Generate article` step で停止したため、`.github/workflows/auto_article.yml:181` の `Bump rotation state after auto-merge` step には到達していない。`origin/main` の HEAD も `9ca5a5a` のままで、`subtopic_seibi` は `1` のまま。期待された `1 -> 2` は発生していない。

判定:

- **PR #58 は効果未確認**
- 理由: inline bump 前に失敗
- 悪化判定: 副作用で悪化した証拠なし

## PR #58 の副作用チェック

確認結果:

- `py -3 -m py_compile scripts/bump_state.py scripts/generate_article.py scripts/topics.py`: OK
- `auto_article.yml` は `PyYAML` で parse OK
- PR #58 の差分は `Bump rotation state after auto-merge` step 追加、`state_update.yml` コメント更新、`subtopic_seibi 0 -> 1`
- `bump_state.py` の引数は workflow から `--pr-body /tmp/pr/body.txt --pr-title ...` で渡されており、CLI 定義と一致
- 7/17 run は `Bump rotation state after auto-merge` より前の `Generate article` step で落ちている

副作用らしい兆候:

- なし

残リスク:

- `bump_state.py` は PR body から category/subtopic を parse できない場合 `return 0` の no-op になる。これは workflow を落とさない設計だが、parse 失敗時に state が進まない可能性は残る。PR #58 の body では PR #55/#56 形式の dry-run equivalent 検証済みとされているが、次回成功 run で実ログ確認が必要。

## 7/10 run との比較

7/10 失敗 run:

- run: `29056371007`
- 実行時刻: 2026-07-09 23:04:36 UTC / 2026-07-10 08:04:36 JST
- 状態: `completed / failure`
- 所要: `1m6s`
- checkout: `origin/main = f07f10b4c3d3db09cf0b30daa58e98d3b5ffa8df`
- topic: `subtopic_index=0` / `新車情報`
- candidate: `新型ハイブリッド国産`
- Tavily: 10 results
- Stage 1 length: 1608
- Stage 2 raw length: 2808
- error: `Stage 2 JSON parse failed: No JSON object found`
- exit code: `6`

今回 7/17 と同じ症状。どちらも Stage 1 までは成功し、Stage 2 が不完全 JSON を返して parse failure。7/10 の「ChatLLM クレジット枯渇疑い」は、ログ上は主因ではなさそう。

## 原因判定

原因:

1. Stage 2 の LLM 応答が JSON として不完全
2. `generate_article.py` が Stage 2 JSON parse error を即 `return 6` で終了
3. 記事ファイル作成前に止まるため PR 作成も merge も inline bump も実行されない

ChatLLM クレジット枯渇/API キー期限切れの可能性:

- 低い
- 根拠: Stage 1/Stage 2 とも API 応答自体は返っている。認証エラー、quota error、timeout、`ChatLLMError` はログに出ていない
- ただし、ChatLLM 側の JSON mode/出力長/finish_reason が不安定な可能性はある。現ログでは `finish_reason` や usage を記録していないため、JSON が途中で切れた理由は未確定

## 修正案 PR ドラフト

推奨 PR:

```text
branch: fix/auto-article-stage2-json-retry
title: fix: Stage 2 JSON 生成失敗時にリトライして raw を診断しやすくする
```

内容:

1. Stage 2 JSON parse failure 時に 2〜3 回リトライ
   - 同じ candidate で「JSON only / no markdown fence / complete object」を再指示
   - 2回目以降は前回 raw の先頭と parse error を修正プロンプトに含める

2. Stage 2 に `max_tokens` を明示
   - 現状 `chatllm.chat(... response_format="json", timeout=240)` で `max_tokens` 未指定
   - raw が `body_markdown` 途中で切れているように見えるため、`max_tokens=6000` などを検討

3. ChatLLM client で `finish_reason` / usage を INFO ログ出力
   - `length` 終了なら出力上限が原因と判断できる
   - quota/auth/rate limit と parse failure を分離できる

4. parse failure 時の raw を artifact または step summary に短縮保存
   - secrets は入らない想定だが、本文 raw なので 2,000〜4,000 chars 程度で十分

5. 可能なら Stage 2 の出力形式を JSON 埋め込み長文から分離
   - 例: frontmatter 相当 JSON + body markdown delimiter
   - 長文 markdown を JSON string に入れる設計は、escape/truncation に弱い

実装候補箇所:

- `scripts/generate_article.py:183` `extract_json()`
- `scripts/generate_article.py:535-555` Stage 2 呼び出しと parse
- `scripts/lib/chatllm_client.py:130-149` `response_format` と応答ログ

## ケンちゃんが取るべきアクション

1. まず ChatLLM クレジット/API キーより、Stage 2 JSON retry 修正 PR を優先
2. 修正後、`workflow_dispatch` で `preview_only=false`、必要なら `category=整備の現場` / `subtopic=整備情報` を指定して手動実行
3. 成功したら PR merge 後の同一 run 内で `Bump rotation state after auto-merge` が実行され、`subtopic_seibi 1 -> 2` になるか確認
4. 次回 run で `subtopic_index=2` / `道路交通法` になれば PR #58 の本命効果確認完了
5. もし Stage 2 retry 修正後も同じように JSON が途切れる場合、ChatLLM 側の出力上限または JSON mode の互換性を疑う

## 現在の最新記事確認

`src/content/blog` の最新:

```text
2026-07-15-2bdedf31.md
2026-07-13-2026-luxion-df34af.md
2026-07-08-n-one-e-45402a.md
```

7/17 の記事ファイルは存在しない。ブログ最新が 7/15 のスライドドア記事のまま、という症状と一致。

## 作業ブランチ

```text
debug/auto-article-fail-20260717
```

作成場所:

```text
C:\Users\kawamoto\Documents\codex-projects\kawatms-blog-debug-auto-article-fail
```
