# Google AdSense 有効化手順

この実装は、AdSense の値が未設定の間は広告スクリプトも広告枠も表示しません。

1. `https://www.google.com/adsense/` でサイト `tsushima-motor.com` を追加し、審査・本人確認を完了する。
2. 自動広告を有効にし、審査をリクエストする。Publisher ID はサイト側で設定済み。
3. 固定広告枠も使う場合だけ、Cloudflare Dashboard の Workers & Pages で build environment variables に以下を追加する。

```text
PUBLIC_ADSENSE_SLOT_ARTICLE_BOTTOM=作成した広告ユニットのslot番号
```

4. 再デプロイ後、ページソースに `ca-pub-1731762204000076` があることを確認する。固定枠を設定した場合だけ、記事末尾に `広告` 表記つきの枠が表示される。
5. AdSense の広告レビューセンターで保険・金融系を優先して確認・ブロックする。広告主やクリエイティブは完全には固定できないため、月1回の見直しを運用に入れる。

旧来の汎用楽天リンクは全記事から削除する。個別商品の紹介を再開する場合は、楽天/A8 で承認済みのリンクと素材だけを `affiliate_catalog.yaml` に追加する。
