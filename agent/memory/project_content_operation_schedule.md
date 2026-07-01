# project_content_operation_schedule

最終更新: 2026-07-01

## Blog 自動記事

- 投稿頻度: 週3回（月・水・金 07:00 JST）
- GitHub Actions cron: `0 22 * * 0,2,4`（UTC 日・火・木 22:00 = JST 月・水・金 07:00）
- 対象カテゴリ: 整備の現場
- サブテーマ: `state/rotation_index.json` の `subtopic_seibi` で 7 件を順番ローテ

## サブテーマ順

0. 新車情報
1. 整備情報
2. 道路交通法
3. 新技術新TEC情報
4. 保険
5. リコール情報
6. 事故の判例

生成成功後に auto-article PR がマージされた場合のみ、`state_update.yml` 経由で `subtopic_seibi` を +1 する。Stage 1 SKIP や preview-only では PR が作られないため、ローテーションは据置。
