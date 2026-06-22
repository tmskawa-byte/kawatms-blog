"""
記事内 H2 セクション画像の生成・配置モジュール。

各 H2 見出しの直下に置く画像を 1 枚ずつ用意する。優先順位:

    1. 手動写真（ケンちゃんの現場写真）が
       public/blog-assets/{slug}/manual-{n}.jpg にあれば最優先で採用
    2. 無ければ Runway / Nano Banana Pro で自動生成して
       public/blog-assets/{slug}/h2-{n}.jpg に保存

生成・取得・保存のいずれかが失敗した H2 は「画像なし」で素通りする
（フォールバック: 画像なし。記事生成そのものは止めない）。

generate_article.py の hero 画像生成（generate_and_save_hero_image）と
同じ ChatLLMClient / image_utils を再利用する。テキストだけ検証したい時や
API キーが無い環境では dry_run=True でモック動作する。
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from scripts.lib.image_utils import (
    ImageFetchError,
    extension_for_mime,
    fetch_image_bytes,
)
from scripts.lib.gemini_image import generate_h2_image, GeminiImageError

LOG = logging.getLogger(__name__)

# 既定の配置先・参照パス
DEFAULT_ASSETS_ROOT = "public/blog-assets"   # ファイルシステム上の保存ルート
DEFAULT_URL_PREFIX = "/blog-assets"          # <img src> / markdown から参照する URL

# 画像モデル設定（HANDOFF: 1024×1024）
IMAGE_MODEL = "nano_banana_pro"
H2_ASPECT_RATIO = "1:1"
H2_RESOLUTION = "1K"

# 手動写真として認める拡張子（優先採用）
MANUAL_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# 画像を生成しない定型見出し（まとめ・参考・関連等）。Runway コスト節約。
# render.py の _SKIP_ENRICH_HEADINGS と意図的に揃えている（疎結合のため別定義）。
DEFAULT_SKIP_HEADINGS = ("まとめ", "参考", "関連記事", "関連サービス", "整備用品をチェック")

# dry_run 時に書き出す 1x1 透明 PNG（プレースホルダ）
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae"
    "426082"
)


def build_prompt(h2_title: str, category: str) -> str:
    """H2 タイトル + カテゴリ + 「対馬の整備工場」キーワードから画像プロンプトを組む。

    断定的・誇張的な表現は避け、写実的な情景描写にとどめる。画像内に文字や
    ロゴは入れない（誤字・不自然な日本語混入を防ぐため）。
    """
    title = (h2_title or "").strip()
    return (
        f"日本の地方にある自動車整備工場の情景。テーマ: 「{title}」。"
        f"記事カテゴリ: {category}。長崎県対馬市の小さな整備工場の雰囲気。"
        "自然光、清潔で実直な作業現場、写実的でやわらかいトーン。"
        "画像内に文字・ロゴ・透かしは入れない。"
    )


def _find_manual_image(assets_dir: str, index: int) -> Optional[str]:
    """manual-{index}.{ext} が存在すればそのファイル名を返す（拡張子つき）。"""
    for ext in MANUAL_EXTS:
        candidate = os.path.join(assets_dir, f"manual-{index}{ext}")
        if os.path.exists(candidate):
            return os.path.basename(candidate)
    return None


def _save_bytes(path: str, data: bytes) -> bool:
    try:
        with open(path, "wb") as f:
            f.write(data)
        return True
    except OSError as e:
        LOG.warning("H2 image save failed (%s): %s", path, e)
        return False


def generate_h2_images(
    slug: str,
    h2_titles: List[str],
    category: str,
    *,
    chatllm=None,
    assets_root: str = DEFAULT_ASSETS_ROOT,
    url_prefix: str = DEFAULT_URL_PREFIX,
    dry_run: bool = False,
    resolution: str = H2_RESOLUTION,
    skip_headings: tuple = DEFAULT_SKIP_HEADINGS,
) -> Dict[int, str]:
    """H2 ごとに画像を用意し、{1-indexed H2 位置: 公開URL} のマップを返す。

    Args:
        slug:        記事 slug。保存先は {assets_root}/{slug}/
        h2_titles:   H2 見出しテキストのリスト（本文の登場順）
        category:    記事カテゴリ（プロンプトに使用）
        chatllm:     ChatLLMClient 互換（generate_image を持つ）。dry_run 以外で必須
        assets_root: 画像保存ルート（テスト時は一時ディレクトリ）
        url_prefix:  markdown から参照する URL プレフィクス
        dry_run:     True なら API を呼ばずプレースホルダ画像を書き出す
        resolution:  生成解像度（既定 "1K" = 1024 相当）

    Returns:
        画像を用意できた H2 位置だけを含むマップ。失敗・スキップした H2 は
        キー自体が入らない（呼び出し側で「画像なし」として扱う）。
    """
    result: Dict[int, str] = {}
    if not h2_titles:
        return result

    assets_dir = os.path.join(assets_root, slug)
    os.makedirs(assets_dir, exist_ok=True)
    public_dir = f"{url_prefix}/{slug}"

    for i, title in enumerate(h2_titles, start=1):
        # 0) まとめ・参考等の定型見出しは画像生成しない（位置 i は消費して整合維持）
        if any(key in (title or "") for key in skip_headings):
            LOG.info("H2 #%d: skip-heading (%s); no image", i, title)
            continue

        # 1) 手動写真があれば最優先
        manual_name = _find_manual_image(assets_dir, i)
        if manual_name:
            result[i] = f"{public_dir}/{manual_name}"
            LOG.info("H2 #%d: manual photo adopted (%s)", i, manual_name)
            continue

        out_name = f"h2-{i}.jpg"
        out_path = os.path.join(assets_dir, out_name)

        # 2-a) dry_run: プレースホルダ画像を書き出すだけ
        if dry_run:
            if _save_bytes(out_path, _PLACEHOLDER_PNG):
                result[i] = f"{public_dir}/{out_name}"
                LOG.info("H2 #%d: dry-run placeholder written (%s)", i, out_name)
            continue

        # 2-b) 本番: Gemini 優先 + ChatLLM フォールバック
        prompt = build_prompt(title, category)
        image_bytes = None
        mime = "image/png"

        # Primary: Gemini API（Nano Banana）
        try:
            image_bytes, mime = generate_h2_image(
                prompt,
                aspect_ratio=H2_ASPECT_RATIO,
            )
            LOG.info("H2 #%d: generated via Gemini API (%d bytes, %s)", i, len(image_bytes), mime)
        except GeminiImageError as e:
            LOG.warning("H2 #%d: Gemini failed: %s; trying ChatLLM fallback", i, e)
            # Fallback: ChatLLM 経路（Phase 2 で撤去予定）
            if chatllm is None:
                LOG.warning("H2 #%d: no chatllm fallback available; skip", i)
                continue
            try:
                image_url_raw = chatllm.generate_image(
                    model=IMAGE_MODEL,
                    prompt=prompt,
                    aspect_ratio=H2_ASPECT_RATIO,
                    resolution=resolution,
                    num_images=1,
                    timeout=360,
                )
                image_bytes, mime = fetch_image_bytes(image_url_raw, timeout=120)
            except Exception as e2:
                LOG.warning("H2 #%d: ChatLLM fallback also failed: %s (skip)", i, e2)
                continue

        # mime に応じた拡張子で保存（既定は .jpg）
        ext = extension_for_mime(mime)
        if ext != ".jpg":
            out_name = f"h2-{i}{ext}"
            out_path = os.path.join(assets_dir, out_name)
        if _save_bytes(out_path, image_bytes):
            result[i] = f"{public_dir}/{out_name}"
            LOG.info("H2 #%d: generated image saved (%s, %d bytes)",
                     i, out_name, len(image_bytes))

    LOG.info("generate_h2_images: %d/%d H2 sections have an image",
             len(result), len(h2_titles))
    return result
