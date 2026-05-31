# Proposed GitHub Workflows

このフォルダには **このリポに最終的に置きたい** GitHub Actions workflow yaml が
入っています。`.github/workflows/` 配下に置くのが正しい位置ですが、本 PR を作る時に
使った Personal Access Token に `workflow` scope が無く、`.github/workflows/`
ファイルを直接 push できませんでした。

## ケンちゃんの作業（マージ前にやる）

GitHub の Web UI から以下の手順で 2 ファイルを `.github/workflows/` に移動して
ください。所要 3 分です。

### 手順

1. この PR の `docs/proposed-workflows/auto_article.yml` をクリック
2. 右上の `...` メニュー → `Edit file` でファイル名のところに
   `.github/workflows/auto_article.yml` と入力（パスごと書き換えで移動になる）
3. `Commit changes` → このブランチ (`feature/auto-article-pipeline`) に直接 commit
4. 同じ手順で `docs/proposed-workflows/state_update.yml` → `.github/workflows/state_update.yml`
5. 不要になった `docs/proposed-workflows/` フォルダを削除（PR に削除 commit を追加）

## あるいはローカルで

`git mv` でも可:

```bash
git checkout feature/auto-article-pipeline
git mv docs/proposed-workflows/auto_article.yml .github/workflows/auto_article.yml
git mv docs/proposed-workflows/state_update.yml .github/workflows/state_update.yml
git rm docs/proposed-workflows/README.md
git commit -m "chore: move proposed workflows into .github/workflows/"
git push
```

## 次回以降

次の自動コミット用 PAT には **`workflow` scope を付ける** ことで、この迂回が
不要になります。`Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Repository permissions → Workflows: Read and write` を ON。
