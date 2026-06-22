"""
新レイアウト（H2画像 / 本文中アフィ / 関連記事）の dry-run 動作確認ハーネス。

API キー無しでも回るように、画像はプレースホルダ（generate_h2_images の
dry_run=True）、アフィは catalog からの候補表示、関連記事は実ファイル走査で
検証する。出力は一時ディレクトリに書き、リポジトリ本体は汚さない。

使い方:
    python scripts/dryrun_layout.py

HANDOFF のテスト方針:
    - 画像生成 → モック（プレースホルダ画像）
    - アフィ挿入 → カタログから候補表示
    - 内部リンク → マッチ結果ログ出力
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.render import render_article, extract_h2_titles, BLOG_DIR
from scripts.affiliates import select_inline_affiliates, load_affiliate_catalog
from scripts.lib.image_generator import generate_h2_images
from scripts.lib.related_posts import load_existing_posts, find_related_posts

logging.basicConfig(level="INFO", format="[%(levelname)s] %(name)s: %(message)s")
LOG = logging.getLogger("dryrun_layout")

SAMPLE_BODY = """こんにちは。対馬モーターサービスです。

この記事では、タイヤ点検の基本を整備士の目線でご紹介します。

## タイヤの空気圧はなぜ大事か

空気圧が不足すると偏摩耗や燃費の悪化につながります。月に一度の点検を私たちはおすすめしています。

## 溝の深さと交換の目安

スリップサインが出たら交換のサインです。残り溝は定期的に確認しておきたいところです。

## タイヤローテーションのコツ

前後の摩耗差を均すために、走行距離 5,000〜10,000km を目安に入れ替えます。

## まとめ

日々の点検が、結果的に出費を抑えることにつながります。
"""

SAMPLE_CATEGORY = "整備の現場"
SAMPLE_TAGS = ["タイヤ", "整備", "点検", "メンテナンス"]


def main() -> int:
    print("=" * 70)
    print("DRY-RUN: blog richer layout")
    print("=" * 70)

    # 1) カタログ読み込み（PyYAML 依存の確認も兼ねる）
    catalog = load_affiliate_catalog()
    print(f"\n[1] affiliate_catalog.yaml: {len(catalog)} compliant items loaded")
    if not catalog:
        print("    !! catalog empty (PyYAML 未導入 or 制約で全除外). "
              "pip install pyyaml で解消するか catalog を確認。")

    # 2) H2 抽出
    h2_titles = extract_h2_titles(SAMPLE_BODY)
    print(f"\n[2] H2 titles ({len(h2_titles)}):")
    for i, t in enumerate(h2_titles, 1):
        print(f"    #{i}: {t}")

    with tempfile.TemporaryDirectory() as tmp:
        assets_root = os.path.join(tmp, "blog-assets")
        out_dir = os.path.join(tmp, "blog")

        # 3) H2 画像（dry_run プレースホルダ）
        h2_image_map = generate_h2_images(
            slug="dryrun-sample",
            h2_titles=h2_titles,
            category=SAMPLE_CATEGORY,
            assets_root=assets_root,
            dry_run=True,
        )
        print(f"\n[3] H2 image map (placeholder): {h2_image_map}")

        # 4) インラインアフィ候補
        inline = select_inline_affiliates(SAMPLE_CATEGORY, SAMPLE_TAGS, max_count=2,
                                          catalog=catalog)
        print(f"\n[4] inline affiliate candidates ({len(inline)}):")
        for a in inline:
            approved = a.get("approved", False)
            print(f"    - {a.get('title')} [approved={approved}] tags={a.get('tags')}")
        print("    （approved=false の間は本文には出力されません＝偽リンク非公開）")

        # 5) 関連記事
        existing = load_existing_posts(BLOG_DIR)
        related = find_related_posts(SAMPLE_CATEGORY, SAMPLE_TAGS, existing, limit=3)
        print(f"\n[5] related posts ({len(related)} of {len(existing)} existing):")
        for p in related:
            print(f"    - {p.slug}  ({p.category})  -> {p.url}")

        # 6) レンダリング（全部入り）
        filepath, slug, used = render_article(
            title="タイヤ点検の基本ガイド（dry-run）",
            description="dry-run 用サンプル記事。",
            body_markdown=SAMPLE_BODY,
            category=SAMPLE_CATEGORY,
            subtopic_key="整備情報",
            pub_dt=datetime(2026, 6, 11),
            dry_run_dir=out_dir,
            hero_image_url="/images/articles/dryrun-sample.png",
            h2_image_map=h2_image_map,
            inline_affiliates=inline,
            related_posts=related,
        )
        print(f"\n[6] rendered: {filepath} (slug={slug}, token-affiliates={used})")

        with open(filepath, "r", encoding="utf-8") as f:
            rendered = f.read()

        print("\n" + "=" * 70)
        print("RENDERED MARKDOWN")
        print("=" * 70)
        print(rendered)

        # ----- 軽い自己検証 -----
        print("=" * 70)
        print("ASSERTIONS")
        print("=" * 70)
        checks = []
        # 画像が各本文 H2 直下に入っている（まとめ除く 3 セクション）
        checks.append(("H2 画像が挿入されている",
                       rendered.count("![") >= len(h2_image_map)))
        # 関連記事セクション
        checks.append(("## 関連記事 セクションがある（関連があれば）",
                       ("## 関連記事" in rendered) or (len(related) == 0)))
        # PR 表記 / 汎用楽天フッターを出さないこと
        checks.append(("PR 表記が冒頭にある", "アフィリエイト" in rendered[:300]))
        checks.append(("汎用楽天フッターが出力されない",
                       "rpx.a8.net" not in rendered and "整備用品をチェック" not in rendered))
        # 未承認アフィは本文に出ていない（💡 行が無い、catalog 全 approved=false 前提）
        any_approved = any(a.get("approved") for a in inline)
        checks.append(("未承認アフィは本文に出力されない",
                       any_approved or ("💡 こちらもどうぞ" not in rendered)))
        # 禁止語（保険/金融）が本文に出ていない
        for bad in ("保険", "投資", "証券", "ローン"):
            checks.append((f"禁止語『{bad}』が本文に無い", bad not in rendered))

        ok = True
        for label, passed in checks:
            print(f"  [{'OK' if passed else 'NG'}] {label}")
            ok = ok and passed

        print("\nRESULT:", "ALL PASS ✅" if ok else "SOME FAILED ❌")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
