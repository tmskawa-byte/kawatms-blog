# Blog Rotation Bump Debug 2026-07-16

## 結論

原因はほぼ特定済み。

`state/rotation_index.json` の `subtopic_seibi` は、2026-07-01 の週3ローテ導入時から `0` のまま一度も進んでいない。

そのため、2026-07-13 の「セレナ LUXION」も、2026-07-15 の「新型ムーヴ」も、どちらも `subtopic_index=0` として生成され、サブテーマが `新車情報` になった。

根本原因は、Auto Article workflow が `GITHUB_TOKEN` で自動 PR merge しているため、後続の `pull_request: closed` で動く `State Update (post-merge)` workflow が起動していないこと。

GitHub 公式 docs でも、`GITHUB_TOKEN` が起こしたイベントは原則として新しい workflow run を作らず、`pull_request` の `closed` も対象外と説明されている。

参考:
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow

## 症状

- 2026-07-13 JST の記事:
  - file: `src/content/blog/2026-07-13-2026-luxion-df34af.md`
  - title: `2026年最新国産ミニバン事情！セレナLUXIONに見る高級化と整備士目線の注意点`
  - PR: https://github.com/tmskawa-byte/kawatms-blog/pull/55
  - expected: `subtopic_index=0` / `新車情報`
  - actual: `subtopic_index=0` / `新車情報`

- 2026-07-15 JST の記事:
  - file: `src/content/blog/2026-07-15-2bdedf31.md`
  - title: `新型ムーヴのスライドドア化と軽EVの波！整備士目線で見る最新軽自動車事情`
  - PR: https://github.com/tmskawa-byte/kawatms-blog/pull/56
  - expected: `subtopic_index=1` / `整備情報`
  - actual: `subtopic_index=0` / `新車情報`

## 調査結果

### 1. `state/rotation_index.json` の現在値と履歴

現在値:

```json
{
  "friday_seibi": 0,
  "sunday_adhoc": 0,
  "subtopic_seibi": 0
}
```

7/1 以降の `state/rotation_index.json` の履歴:

```text
635f9cd 2026-07-01 13:44:27 +0900 feat: rotate blog subtopics weekly (#48)
```

つまり、週3ローテ導入後に `subtopic_seibi` を進める state commit が一度も入っていない。

### 2. `state_update.yml` / `bump_state.py` の bump 処理

処理自体は存在する。

`.github/workflows/state_update.yml`:

```yaml
on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  bump_state:
    if: |
      github.event.pull_request.merged == true &&
      contains(github.event.pull_request.labels.*.name, 'auto-article')
```

`scripts/bump_state.py`:

```python
if category == "整備の現場":
    rotation["subtopic_seibi"] = (
        rotation["subtopic_seibi"] + 1
    ) % SEIBI_SUBTOPIC_ROTATION_LEN
```

PR #55 / #56 の body には以下が含まれており、`bump_state.py` が実行されれば parse 可能。

```text
- カテゴリ: 整備の現場
- サブトピック: 新車情報
```

PR #55 / #56 には `auto-article` ラベルも付いている。

### 3. `generate_article.py` の rotation 参照

`scripts/generate_article.py` は `state/rotation_index.json` を読み、`rotation["subtopic_seibi"]` を `determine_topic()` に渡している。

実行経路上、曜日固定でサブテーマを決める古いロジックは残っていない。

ログ用に `weekday` は残っているが、サブテーマ決定には使われていない。

```python
rotation = read_rotation_index()

category, subtopic_key, meta = determine_topic(
    rotation["subtopic_seibi"],
)
```

### 4. `topics.py` の `determine_topic()`

`determine_topic()` は `subtopic_index % 7` で以下の順番を返す。

```python
SEIBI_SUBTOPIC_ROTATION = [
    "新車情報",
    "整備情報",
    "道路交通法",
    "新技術新TEC情報",
    "保険",
    "リコール情報",
    "事故の判例",
]
```

ローカル確認結果:

```text
0: 整備の現場 / 新車情報
1: 整備の現場 / 整備情報
2: 整備の現場 / 道路交通法
3: 整備の現場 / 新技術新TEC情報
4: 整備の現場 / 保険
5: 整備の現場 / リコール情報
6: 整備の現場 / 事故の判例
7: 整備の現場 / 新車情報
```

### 5. 7/13・7/15 の Auto Article Actions ログ

#### 2026-07-13 JST / run `29211965546`

```text
Determined topic: weekday=0, subtopic_index=0, category=整備の現場, subtopic_key=新車情報
Candidate: 新型ミニバン 国産
```

PR body:

```text
- カテゴリ: 整備の現場
- サブトピック: 新車情報
- 検索キーワード: 新型ミニバン 国産
```

#### 2026-07-15 JST / run `29374316373`

```text
Determined topic: weekday=2, subtopic_index=0, category=整備の現場, subtopic_key=新車情報
Candidate: 新型軽自動車
```

PR body:

```text
- カテゴリ: 整備の現場
- サブトピック: 新車情報
- 検索キーワード: 新型軽自動車
```

#### 比較: 2026-07-08 JST / run `28904338141`

```text
Determined topic: weekday=2, subtopic_index=0, category=整備の現場, subtopic_key=新車情報
```

7/8 時点からすでに `subtopic_index=0` 固定になっていた。

## State Update workflow の実行状況

`State Update (post-merge)` の workflow run は 2026-07-06 以降、auto article PR merge に対して起動していない。

確認した実行履歴:

```text
2026-07-06 fix/blog-20260706-factcheck -> skipped
2026-07-03 feat/gbp-api-direct-integration -> skipped
2026-07-03 fix/latest-blog-hero-text -> skipped
2026-07-01 feat/blog-weekly3-subtopic-rotation -> skipped
```

PR #55 / #56 の `pull_request: closed` に対応する `State Update` run は見当たらなかった。

## 原因

`auto_article.yml` の `Merge generated article` step は以下のように `GITHUB_TOKEN` で PR を merge している。

```yaml
env:
  GH_TOKEN: ${{ github.token }}
run: |
  gh pr merge "${{ steps.cpr.outputs.pull-request-number }}" \
    --squash \
    --delete-branch \
    --subject "feat(blog): auto-generated article — ${{ steps.gen.outputs.title }}"
```

GitHub Actions の仕様として、`GITHUB_TOKEN` が起こした `pull_request: closed` イベントは、別 workflow を新しく起動しない。

そのため、`state_update.yml` は「auto-article PR が merge されたら state を bump する」設計だが、自動 merge の場合は肝心の workflow が起動しない。

このため `state/rotation_index.json` が `0` のまま固定され、毎回 `新車情報` が選ばれている。

## 修正案

### 推奨案 A: `auto_article.yml` 内で merge 後に直接 `bump_state.py` を実行する

`GITHUB_TOKEN` による後続 workflow 起動に依存しないため、最も確実。

概要:

1. `Merge generated article` step の後に `Bump rotation state` step を追加
2. `steps.gen.outputs.pr_body` を一時ファイルへ保存
3. `python scripts/bump_state.py --pr-body /tmp/pr_body.txt --pr-title "${{ steps.gen.outputs.title }}"`
4. `state/rotation_index.json` / `state/recent_subtopics.json` に差分があれば commit & push

注意点:

- `gh pr merge` 後に `git fetch origin main && git checkout main && git reset --hard origin/main` で最新 main に合わせてから state commit する
- `state_update.yml` は手動 merge / 人間 merge 用の fallback として残してよい
- 自動 merge 時は inline bump、手動 merge 時は `state_update.yml` という二段構えにする

### 案 B: `auto_article.yml` から `repository_dispatch` / `workflow_dispatch` で state update を起動する

GitHub docs 上、`repository_dispatch` / `workflow_dispatch` は `GITHUB_TOKEN` 起点でも workflow run を作れる例外。

ただし payload 受け渡しと workflow 側の分岐が増えるため、A案より複雑。

### 案 C: PAT / GitHub App token で PR merge する

`GITHUB_TOKEN` ではなく PAT または GitHub App token で merge すれば、`pull_request: closed` workflow が起動できる。

ただし新しい secret 管理が必要。既存契約・既存構成優先の方針から、まずは A案が無難。

## 一時復旧案

現在 `subtopic_seibi` は `0`。

次回投稿を期待通り `整備情報` にするなら、手動で以下にする。

```json
"subtopic_seibi": 1
```

ただし、失敗した bump を機械的に2回分反映すると `2` になる。

実際の公開記事は `新車情報` が連続しているので、コンテンツの並びを自然に戻す目的なら `1` 推奨。

## PR ドラフト提案

実装 PR 案:

- branch: `fix/blog-rotation-bump-inline-after-auto-merge`
- title: `fix: auto article merge 後に rotation_index を直接 bump`
- changes:
  - `.github/workflows/auto_article.yml`
    - merge 後に `bump_state.py` 実行 step を追加
    - state 差分があれば `chore(state): bump rotation after auto article merge [skip ci]` で main push
  - `state/rotation_index.json`
    - 一時復旧として `subtopic_seibi: 1`
  - 必要なら `state_update.yml`
    - コメントに「manual merge fallback」と明記

検証:

- `py -3 -m py_compile scripts/bump_state.py scripts/generate_article.py scripts/topics.py`
- `bump_state.py` を PR #55 相当の body で dry-run 相当実行し `0 -> 1` を確認
- `bump_state.py` を PR #56 相当の body で連続実行し `1 -> 2` を確認
- workflow YAML の構文確認

## 調査コマンドメモ

```powershell
git log --since='2026-07-01' --pretty=format:'%h %ad %s' --date=iso -- state/rotation_index.json
gh run list --repo tmskawa-byte/kawatms-blog --workflow "State Update (post-merge)" --limit 20
gh run view 29211965546 --repo tmskawa-byte/kawatms-blog --log
gh run view 29374316373 --repo tmskawa-byte/kawatms-blog --log
gh pr view 55 --repo tmskawa-byte/kawatms-blog --json number,title,mergedAt,labels,body,url,mergeCommit
gh pr view 56 --repo tmskawa-byte/kawatms-blog --json number,title,mergedAt,labels,body,url,mergeCommit
```
