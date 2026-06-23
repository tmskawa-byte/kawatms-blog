"""
kawatms-blog 記事自動生成のメインエントリ。

Pipeline:
    1. JST 曜日 + rotation_index → (category, subtopic_key, meta) 決定
    2. subtopic_key 内の candidates から直近5件除外で抽選
    3. Tavily search (news, domains 指定)
    4. Stage 1: 調査メモ生成 (Gemini 3.1 Pro Preview)
       - SKIP 判定なら exit 0
    5. Stage 2: 記事本文 + メタ JSON 生成
    5.5 Stage 2.5: ヒーロー画像プロンプト生成 (Gemini)
    5.6 Stage 2.6: 画像生成 (Nano Banana Pro) → public/images/articles/{slug}.{ext}
    6. アフィリエイト挿入 + PR 表記付与 + slug 化 → src/content/blog/*.md
    7. dry-run でなければ summary を stdout に出力（workflow が PR 作成に使う）

画像生成は --skip-image で OFF にできる（テキストだけテストしたい時）。
画像生成が失敗しても記事生成は継続（heroImage なしで render）。

Env:
    CHATLLM_API_KEY, TAVILY_API_KEY

CLI:
    --dry-run         : .md 生成までやって PR は作らない（summary は出さない）
    --category NAME   : カテゴリ強制（曜日ロジック bypass）
    --subtopic KEY    : サブトピックキー強制
    --candidate STR   : 検索キーワード強制
    --seed N          : 抽選決定論化
    --preview-only    : トピック決定だけ表示して即終了
    --out-dir PATH    : 出力先ディレクトリ override（テスト用）
    --skip-image      : ヒーロー画像生成をスキップ（テキストだけ）
    --image-out-dir P : ヒーロー画像保存先 override（テスト用）
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# repo root を sys.path に追加（scripts.* / prompts.* import のため）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.lib.chatllm_client import ChatLLMClient, ChatLLMError
from scripts.lib.tavily_client import TavilyClient, TavilyError
from scripts.lib.image_utils import (
    ImageFetchError,
    extension_for_mime,
    fetch_image_bytes,
)
from scripts.lib.gemini_image import generate_hero_image, GeminiImageError
from scripts.topics import (
    CATEGORY_SUBTOPICS,
    SEIBI_SUBTOPICS,
    FRIDAY_ROTATION,
    determine_topic,
    build_query,
)
from scripts.affiliates import build_affiliate_hint, select_inline_affiliates
from scripts.render import render_article, slugify, extract_h2_titles, BLOG_DIR
from scripts.lib.image_generator import generate_h2_images
from scripts.lib.related_posts import load_existing_posts, find_related_posts
from prompts.system import PERSONA_HEADER  # noqa: F401  (imported for completeness)
from prompts.stage1_research import (
    STAGE1_SYSTEM_PROMPT,
    format_articles_for_llm,
    is_skip,
)
from prompts.stage2_article import (
    STAGE2_SYSTEM_PROMPT,
    build_stage2_user_input,
    format_recent_subtopics_for_prompt,
)
from prompts.hero_image import (
    HERO_IMAGE_SYSTEM_PROMPT,
    build_hero_image_user_input,
)
from prompts.templates import get_template

LOG = logging.getLogger("generate_article")

TEXT_MODEL = "gemini-3.1-pro-preview"
IMAGE_MODEL = "nano_banana_pro"
HERO_ASPECT_RATIO = "16:9"
HERO_RESOLUTION = "2K"

STATE_DIR = os.path.join(_REPO_ROOT, "state")
RECENT_SUBTOPICS_FILE = os.path.join(STATE_DIR, "recent_subtopics.json")
ROTATION_INDEX_FILE = os.path.join(STATE_DIR, "rotation_index.json")

# 画像保存先（public/images/articles/）。public/ 配下なので Astro がそのまま配信する。
HERO_IMAGE_DIR = os.path.join(_REPO_ROOT, "public", "images", "articles")
# 記事 frontmatter / <img src> から参照するときの URL パス（先頭 / 必須）
HERO_IMAGE_URL_PREFIX = "/images/articles"

SUBTOPIC_EXCLUDE_WINDOW = 5
SUBTOPIC_HISTORY_KEEP = 20


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


# ---------------------------------------------------------------------------
# State IO
# ---------------------------------------------------------------------------
def read_rotation_index() -> Dict[str, int]:
    try:
        with open(ROTATION_INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "friday_seibi": int(data.get("friday_seibi", 0)),
            "sunday_adhoc": int(data.get("sunday_adhoc", 0)),
        }
    except (FileNotFoundError, ValueError, OSError) as e:
        LOG.warning("rotation_index.json unreadable (%s); defaulting to 0/0", e)
        return {"friday_seibi": 0, "sunday_adhoc": 0}


def read_recent_subtopics() -> List[Dict[str, Any]]:
    try:
        with open(RECENT_SUBTOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        hist = data.get("history", []) or []
        return hist if isinstance(hist, list) else []
    except (FileNotFoundError, ValueError, OSError) as e:
        LOG.warning("recent_subtopics.json unreadable (%s); starting empty", e)
        return []


# ---------------------------------------------------------------------------
# JST helpers
# ---------------------------------------------------------------------------
JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    return datetime.now(JST)


# ---------------------------------------------------------------------------
# Subtopic candidate selection (dedup window)
# ---------------------------------------------------------------------------
def pick_candidate_with_dedup(
    candidates: List[str],
    history: List[Dict[str, Any]],
    rng: random.Random,
) -> str:
    recent_titles = {
        h.get("candidate") or h.get("subtopic_candidate")
        for h in history[-SUBTOPIC_EXCLUDE_WINDOW:]
        if isinstance(h, dict)
    }
    available = [c for c in candidates if c not in recent_titles]
    if not available:
        LOG.warning(
            "All %d candidates appear in last %d history entries; falling back.",
            len(candidates), SUBTOPIC_EXCLUDE_WINDOW,
        )
        available = candidates
    chosen = rng.choice(available)
    LOG.info("Candidate pick: %r (from %d available)", chosen, len(available))
    return chosen


# ---------------------------------------------------------------------------
# JSON extraction (Stage 2)
# ---------------------------------------------------------------------------
def extract_json(text: str) -> Dict[str, Any]:
    if not text or not text.strip():
        raise ValueError("Empty response")
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found: {s[:200]}")
    return json.loads(s[start : end + 1])


# ---------------------------------------------------------------------------
# Hero image: prompt → bytes → save → URL
# ---------------------------------------------------------------------------
def generate_and_save_hero_image(
    chatllm: ChatLLMClient,
    title: str,
    description: str,
    category: str,
    subtopic_key: str,
    slug: str,
    out_dir: str,
    url_prefix: str,
) -> Optional[Tuple[str, str]]:
    """
    Stage 2.5 (prompt 生成) + 2.6 (画像生成 + 保存) をまとめて実行。

    Returns: (saved_filepath, public_url) on success, None on failure.
    失敗は raise せずに None を返す（heroImage なしで記事は継続生成する）。
    """
    # ----- Stage 2.5: prompt 生成 -----
    try:
        user_input = build_hero_image_user_input(
            title=title,
            description=description,
            category=category,
            subtopic_key=subtopic_key,
        )
        LOG.info("Stage 2.5 (hero image prompt) starting...")
        image_prompt = chatllm.chat(
            model=TEXT_MODEL,
            system=HERO_IMAGE_SYSTEM_PROMPT,
            user=user_input,
            timeout=120,
        )
        image_prompt = (image_prompt or "").strip()
        # Markdown コードフェンスや先頭引用符を剥がす
        if image_prompt.startswith("```"):
            image_prompt = re.sub(r"^```[a-zA-Z]*\n", "", image_prompt)
            image_prompt = re.sub(r"\n```$", "", image_prompt)
            image_prompt = image_prompt.strip()
        if not image_prompt:
            LOG.warning("Hero image prompt is empty; skipping image generation")
            return None
        LOG.info("Hero image prompt: %d chars; head: %s",
                 len(image_prompt), image_prompt[:200].replace("\n", " "))
    except ChatLLMError as e:
        LOG.warning("Hero image prompt generation failed: %s (continuing without image)", e)
        return None

    # ----- Stage 2.6: 画像生成（Gemini 優先 + ChatLLM フォールバック）-----
    image_bytes: Optional[bytes] = None
    mime: str = "image/png"

    # Primary: Gemini API（Nano Banana Pro）
    try:
        LOG.info("Generating hero image via Gemini API (Nano Banana Pro)...")
        image_bytes, mime = generate_hero_image(
            image_prompt,
            aspect_ratio=HERO_ASPECT_RATIO,
            image_size=HERO_RESOLUTION,
        )
        LOG.info("Hero image generated via Gemini API: %d bytes, %s", len(image_bytes), mime)
    except GeminiImageError as e:
        LOG.warning("Gemini hero image failed: %s; falling back to ChatLLM route", e)

    # Fallback: ChatLLM 経路（Phase 2 で撤去予定）
    if image_bytes is None:
        try:
            LOG.info("Generating hero image via ChatLLM (%s, %s, %s)...",
                     IMAGE_MODEL, HERO_ASPECT_RATIO, HERO_RESOLUTION)
            image_url_raw = chatllm.generate_image(
                model=IMAGE_MODEL,
                prompt=image_prompt,
                aspect_ratio=HERO_ASPECT_RATIO,
                resolution=HERO_RESOLUTION,
                num_images=1,
                timeout=360,
            )
        except ChatLLMError as e:
            LOG.warning("Hero image generation failed (ChatLLM): %s (continuing without image)", e)
            return None

        LOG.info("Image URL kind: %s",
                 "data-url" if image_url_raw.startswith("data:") else "http")

        try:
            image_bytes, mime = fetch_image_bytes(image_url_raw, timeout=120)
        except ImageFetchError as e:
            LOG.warning("Image fetch failed: %s (continuing without image)", e)
            return None

    LOG.info("Image bytes: %d, mime: %s", len(image_bytes), mime)

    # ----- 保存 -----
    ext = extension_for_mime(mime)
    filename = f"{slug}{ext}"
    os.makedirs(out_dir, exist_ok=True)
    filepath = os.path.join(out_dir, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(image_bytes)
    except OSError as e:
        LOG.warning("Image save failed: %s (continuing without image)", e)
        return None

    public_url = f"{url_prefix}/{filename}"
    LOG.info("Hero image saved: %s (public URL: %s)", filepath, public_url)
    return filepath, public_url


# ---------------------------------------------------------------------------
# Workflow output (GitHub Actions $GITHUB_OUTPUT 用)
# ---------------------------------------------------------------------------
def write_gh_output(key: str, value: str) -> None:
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if not gh_out:
        return
    safe = value.replace("\r", "")
    if "\n" in safe:
        delim = f"EOF_{key}_{os.urandom(4).hex()}"
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"{key}<<{delim}\n{safe}\n{delim}\n")
    else:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"{key}={safe}\n")


def write_gh_summary(text: str) -> None:
    gh_sum = os.environ.get("GITHUB_STEP_SUMMARY")
    if not gh_sum:
        return
    with open(gh_sum, "a", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="kawatms-blog article generator")
    p.add_argument("--dry-run", action="store_true",
                   help=".md 生成までやって PR 作成 step に signal を送らない")
    p.add_argument("--category", default=None,
                   help="カテゴリ強制（曜日ロジック bypass）")
    p.add_argument("--subtopic", default=None,
                   help="サブトピックキー強制")
    p.add_argument("--candidate", default=None,
                   help="検索キーワード強制（直近除外 bypass）")
    p.add_argument("--seed", type=int, default=None,
                   help="抽選決定論化")
    p.add_argument("--preview-only", action="store_true",
                   help="トピック決定だけ表示して即終了")
    p.add_argument("--out-dir", default="",
                   help="出力ディレクトリ override（テスト用）")
    p.add_argument("--max-tavily-results", type=int, default=10)
    p.add_argument("--max-stage1-attempts", type=int, default=4,
                   help="Stage 1 が SKIP した場合に別 candidate で再試行する最大回数")
    p.add_argument("--skip-image", action="store_true",
                   help="ヒーロー画像 + H2 画像生成をスキップ（テキストだけ）")
    p.add_argument("--image-out-dir", default="",
                   help="ヒーロー画像保存ディレクトリ override（テスト用）")
    p.add_argument("--rich-layout", action="store_true",
                   help="新レイアウト（H2画像 + 本文中アフィ + 関連記事）を有効化。"
                        "未指定でも環境変数 RICH_LAYOUT=1 で有効化できる。")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    setup_logging()
    args = parse_args()

    LOG.info("=== kawatms-blog auto article: %s ===",
             now_jst().isoformat())

    rng = random.Random(args.seed) if args.seed is not None else random
    today_jst = now_jst()
    weekday = today_jst.weekday()  # 0=月
    rotation = read_rotation_index()
    history = read_recent_subtopics()

    # ----- 1. category / subtopic_key 決定 -----
    if args.category and args.subtopic:
        category = args.category
        subtopic_key = args.subtopic
        cat_subs = CATEGORY_SUBTOPICS.get(category, {})
        if subtopic_key not in cat_subs:
            LOG.error("Invalid --subtopic %r for category %r (valid: %s)",
                      subtopic_key, category, list(cat_subs.keys()))
            return 2
        meta = cat_subs[subtopic_key]
        LOG.info("Topic forced via CLI: %s / %s", category, subtopic_key)
    elif args.category:
        category = args.category
        cat_subs = CATEGORY_SUBTOPICS.get(category)
        if not cat_subs:
            LOG.error("Invalid --category %r", category)
            return 2
        # 整備の現場でサブ未指定なら weekday から推測、それ以外は _default
        if category == "整備の現場":
            _, subtopic_key, meta = determine_topic(
                weekday,
                rotation["friday_seibi"],
                rotation["sunday_adhoc"],
            )
            if subtopic_key not in cat_subs:
                subtopic_key = "整備情報"
                meta = SEIBI_SUBTOPICS[subtopic_key]
        else:
            subtopic_key = "_default"
            meta = cat_subs["_default"]
    else:
        category, subtopic_key, meta = determine_topic(
            weekday,
            rotation["friday_seibi"],
            rotation["sunday_adhoc"],
        )

    LOG.info("Determined topic: weekday=%d, category=%s, subtopic_key=%s",
             weekday, category, subtopic_key)

    # ----- 2. candidate 抽選 -----
    if args.candidate:
        candidate = args.candidate
    else:
        candidate = pick_candidate_with_dedup(
            meta["candidates"], history, rng,
        )
    LOG.info("Candidate: %s", candidate)

    if args.preview_only:
        LOG.info("=== PREVIEW ONLY: exit before Tavily ===")
        write_gh_output("category", category)
        write_gh_output("subtopic_key", subtopic_key)
        write_gh_output("candidate", candidate)
        return 0

    chatllm = ChatLLMClient()
    recent_block = format_recent_subtopics_for_prompt(history)
    max_attempts = 1 if args.candidate else max(1, args.max_stage1_attempts)
    tried_candidates: List[str] = []
    articles: List[Dict[str, Any]] = []
    memo = ""

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            remaining = [c for c in meta["candidates"] if c not in tried_candidates]
            if not remaining:
                LOG.warning("No remaining candidates for Stage 1 retry.")
                break
            candidate = pick_candidate_with_dedup(remaining, history, rng)
            LOG.info("Retry candidate: %s", candidate)
        tried_candidates.append(candidate)

        # ----- 3. Tavily search -----
        try:
            tavily = TavilyClient()
            query = build_query(category, subtopic_key, candidate)
            LOG.info("Tavily query (attempt %d/%d): %s", attempt, max_attempts, query)
            articles = tavily.search(
                query=query,
                topic="news",
                max_results=args.max_tavily_results,
                days=180,
                include_domains=meta["domains"],
            )
        except TavilyError as e:
            LOG.error("Tavily failure: %s", e)
            return 3
        LOG.info("Got %d article(s)", len(articles))

        # ----- 4. Stage 1 -----
        user_input_1 = format_articles_for_llm(
            articles, category, subtopic_key, candidate,
            recent_posts_block=recent_block,
        )
        try:
            LOG.info("Stage 1 (research memo) starting...")
            memo = chatllm.chat(
                model=TEXT_MODEL,
                system=STAGE1_SYSTEM_PROMPT,
                user=user_input_1,
                timeout=240,
            )
        except ChatLLMError as e:
            LOG.error("Stage 1 failed: %s", e)
            return 4
        LOG.info("Stage 1 length: %d", len(memo))
        LOG.info("Stage 1 head: %s", memo[:200].replace("\n", " "))

        if not is_skip(memo):
            break

        skip_head = memo.strip().splitlines()[0] if memo.strip() else "SKIP"
        LOG.warning(
            "Stage 1 returned SKIP on attempt %d/%d. candidate=%r reason=%r",
            attempt,
            max_attempts,
            candidate,
            skip_head,
        )
        write_gh_output("skip_reason", skip_head)

    if not memo or is_skip(memo):
        summary = (
            "### Auto Article skipped\n\n"
            f"- category: {category}\n"
            f"- subtopic_key: {subtopic_key}\n"
            f"- tried_candidates: {', '.join(tried_candidates) if tried_candidates else '(none)'}\n"
        )
        write_gh_summary(summary)
        return 0

    # ----- 5. Stage 2 -----
    aff_hint = build_affiliate_hint(category, subtopic_key)
    template_hint = get_template(category, subtopic_key)
    full_hint = (aff_hint + "\n\n" + template_hint).strip()

    user_input_2 = build_stage2_user_input(
        memo, category, subtopic_key, candidate,
        recent_posts_block=recent_block,
        affiliate_hint=full_hint,
    )
    try:
        LOG.info("Stage 2 (article body) starting...")
        stage2_raw = chatllm.chat(
            model=TEXT_MODEL,
            system=STAGE2_SYSTEM_PROMPT,
            user=user_input_2,
            response_format="json",
            timeout=240,
        )
    except ChatLLMError as e:
        LOG.error("Stage 2 failed: %s", e)
        return 5
    LOG.info("Stage 2 raw length: %d", len(stage2_raw))

    try:
        stage2 = extract_json(stage2_raw)
    except (ValueError, json.JSONDecodeError) as e:
        LOG.error("Stage 2 JSON parse failed: %s\nraw=%s", e, stage2_raw[:1000])
        return 6

    title = (stage2.get("title") or "").strip()
    description = (stage2.get("description") or "").strip()
    body_markdown = (stage2.get("body_markdown") or "").strip()
    tags = stage2.get("tags") or []
    if not title or not body_markdown:
        LOG.error("Stage 2 missing fields: title=%r body_len=%d",
                  title[:60], len(body_markdown))
        return 6

    # ----- 5.5 / 5.6: hero image -----
    # render より先に slug を決めて、ファイル名を hero image と一致させる
    date_str = today_jst.strftime("%Y-%m-%d")
    slug = slugify(title, date_str)

    hero_image_url: Optional[str] = None
    if args.skip_image:
        LOG.info("--skip-image given; skipping hero image generation")
    else:
        image_out_dir = args.image_out_dir or HERO_IMAGE_DIR
        result = generate_and_save_hero_image(
            chatllm=chatllm,
            title=title,
            description=description,
            category=category,
            subtopic_key=subtopic_key,
            slug=slug,
            out_dir=image_out_dir,
            url_prefix=HERO_IMAGE_URL_PREFIX,
        )
        if result is not None:
            _saved_path, hero_image_url = result

    # ----- 5.7 新レイアウト: H2 画像 / 本文中アフィ / 関連記事 -----
    rich_layout = args.rich_layout or os.environ.get("RICH_LAYOUT") == "1"
    h2_image_map: Dict[int, str] = {}
    inline_affiliates: List[Dict[str, Any]] = []
    related: List[Any] = []
    if rich_layout:
        h2_titles = extract_h2_titles(body_markdown)
        LOG.info("Rich layout ON: %d H2 sections detected", len(h2_titles))

        # H2 画像（--skip-image なら省略。dry-run はプレースホルダ）
        if args.skip_image:
            LOG.info("--skip-image given; skipping H2 image generation")
        elif h2_titles:
            try:
                h2_image_map = generate_h2_images(
                    slug=slug,
                    h2_titles=h2_titles,
                    category=category,
                    chatllm=chatllm,
                    dry_run=args.dry_run,
                )
            except Exception as e:  # 画像失敗で記事生成は止めない
                LOG.warning("H2 image generation error: %s (continuing)", e)

        # 本文中インラインアフィ（カテゴリ・タグマッチ、最大 2 個）
        try:
            inline_affiliates = select_inline_affiliates(category, tags, max_count=2)
            LOG.info("Inline affiliate candidates: %s",
                     [a.get("title") for a in inline_affiliates] or "(none)")
        except Exception as e:
            LOG.warning("Inline affiliate selection error: %s (continuing)", e)

        # 関連記事（カテゴリ・タグマッチ、2〜3 件）
        try:
            existing = load_existing_posts(BLOG_DIR)
            related = find_related_posts(
                category, tags, existing, exclude_slug=slug, limit=3,
            )
            LOG.info("Related posts: %s",
                     [getattr(p, "slug", "?") for p in related] or "(none)")
        except Exception as e:
            LOG.warning("Related posts error: %s (continuing)", e)

    # ----- 6. Render markdown -----
    try:
        filepath, slug_out, used_aff = render_article(
            title=title,
            description=description,
            body_markdown=body_markdown,
            category=category,
            subtopic_key=subtopic_key,
            pub_dt=today_jst,
            dry_run_dir=args.out_dir,
            hero_image_url=hero_image_url,
            h2_image_map=h2_image_map,
            inline_affiliates=inline_affiliates,
            related_posts=related,
        )
    except (ValueError, OSError) as e:
        LOG.error("Render failed: %s", e)
        return 7

    # slug が事前計算と一致することを確認（不整合があれば warn）
    if slug_out != slug:
        LOG.warning("Slug mismatch: pre-computed=%s, render returned=%s. "
                    "Hero image filename may not match article slug.",
                    slug, slug_out)

    word_count = len(body_markdown)
    LOG.info("=== Generated: %s (%d chars, hero=%s) ===",
             filepath, word_count, hero_image_url or "(none)")

    # ----- 7. Workflow output -----
    write_gh_output("category", category)
    write_gh_output("subtopic_key", subtopic_key)
    write_gh_output("candidate", candidate)
    write_gh_output("title", title)
    write_gh_output("slug", slug_out)
    write_gh_output("filepath", filepath)
    write_gh_output("word_count", str(word_count))
    write_gh_output("used_affiliates", ", ".join(used_aff) if used_aff else "(none)")
    write_gh_output("hero_image", hero_image_url or "(none)")
    write_gh_output("rich_layout", "true" if rich_layout else "false")
    write_gh_output("h2_image_count", str(len(h2_image_map)))
    write_gh_output(
        "inline_affiliate_candidates",
        ", ".join(a.get("title", "?") for a in inline_affiliates) if inline_affiliates else "(none)",
    )
    write_gh_output(
        "related_posts",
        ", ".join(getattr(p, "slug", "?") for p in related) if related else "(none)",
    )
    # for body of PR
    pr_body = (
        f"AI が自動生成した記事の PR です。\n\n"
        f"- カテゴリ: {category}\n"
        f"- サブトピック: {subtopic_key}\n"
        f"- 検索キーワード: {candidate}\n"
        f"- 文字数: {word_count}\n"
        f"- 採用アフィリエイト: {', '.join(used_aff) if used_aff else '(なし)'}\n"
        f"- タグ: {', '.join(tags) if tags else '(なし)'}\n"
        f"- ヒーロー画像: {hero_image_url or '(なし)'}\n"
        f"- リッチレイアウト: {'ON' if rich_layout else 'OFF'}"
        + (
            f"（H2画像 {len(h2_image_map)} 枚 / "
            f"本文中アフィ候補 {len(inline_affiliates)} 件 / "
            f"関連記事 {len(related)} 件）\n\n"
            if rich_layout else "\n\n"
        )
        + f"## レビュー手順\n"
        f"1. Cloudflare Pages のプレビュー URL（このコメントに自動付与されます）で表示確認\n"
        f"2. 編集が必要なら GitHub Web / Mobile で `{filepath.replace(_REPO_ROOT + '/', '')}` を直接編集\n"
        f"3. 問題なければ Merge → main → Cloudflare 自動デプロイ\n"
        f"4. このラベル `auto-article` がついたままマージすると、"
        f"`state_update.yml` が `state/rotation_index.json` と "
        f"`state/recent_subtopics.json` を自動更新します\n"
    )
    write_gh_output("pr_body", pr_body)

    # Step summary
    write_gh_summary(
        f"## 📝 Generated article\n\n"
        f"- **{title}**\n"
        f"- {category} / {subtopic_key} / {candidate}\n"
        f"- {word_count} chars\n"
        f"- file: `{filepath}`\n"
        f"- hero: `{hero_image_url or '(none)'}`\n\n"
    )

    if args.dry_run:
        LOG.warning("DRY RUN: PR step will be skipped. State will NOT advance.")
        write_gh_output("dry_run", "true")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
