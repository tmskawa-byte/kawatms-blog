"""
PR マージ後に呼ばれる state 更新スクリプト。

`.github/workflows/state_update.yml` から `pull_request: closed (merged=true)`
イベントで起動。

- マージされた PR から `category` / `subtopic_key` / `candidate` / `title` を
  PR body から正規表現で抽出
- state/recent_subtopics.json に履歴を追記（最大 SUBTOPIC_HISTORY_KEEP 件）
- 金曜の整備記事なら state/rotation_index.json の friday_seibi を進める
- 日曜のアドホック記事なら sunday_adhoc を進める

CLI:
    --pr-body PATH    : PR body を書き出した一時ファイルのパス（必須）
    --merged-date STR : マージ日（YYYY-MM-DD、JST）。省略時は今日
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

LOG = logging.getLogger("bump_state")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(_REPO_ROOT, "state")
ROTATION_INDEX_FILE = os.path.join(STATE_DIR, "rotation_index.json")
RECENT_SUBTOPICS_FILE = os.path.join(STATE_DIR, "recent_subtopics.json")

SUBTOPIC_HISTORY_KEEP = 20
JST = timezone(timedelta(hours=9))

FRIDAY_ROTATION_LEN = 3   # 道路交通法 / 新技術新TEC / 保険
SUNDAY_ROTATION_LEN = 2   # AI / 対馬


def setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def parse_pr_body(body: str) -> Dict[str, str]:
    """PR body から各フィールドを抽出。

    generate_article.py が PR body に書く以下を期待:
        - カテゴリ: 整備の現場
        - サブトピック: 保険
        - 検索キーワード: 自動車保険 見直し
        - 文字数: 2300
    """
    result: Dict[str, str] = {}
    patterns = {
        "category": r"-\s*カテゴリ\s*[:：]\s*(.+)",
        "subtopic": r"-\s*サブトピック\s*[:：]\s*(.+)",
        "candidate": r"-\s*検索キーワード\s*[:：]\s*(.+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, body)
        if m:
            result[key] = m.group(1).strip()
    return result


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


def write_rotation_index(d: Dict[str, int]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    # preserve comments
    payload = {
        "friday_seibi": d.get("friday_seibi", 0),
        "sunday_adhoc": d.get("sunday_adhoc", 0),
        "_comment_friday": "0=道路交通法, 1=新技術新TEC, 2=保険 (mod 3)",
        "_comment_sunday": "0=AI・自動化, 1=対馬ライフ (mod 2)",
    }
    with open(ROTATION_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_recent_subtopics() -> List[Dict[str, Any]]:
    try:
        with open(RECENT_SUBTOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        hist = data.get("history", []) or []
        return hist if isinstance(hist, list) else []
    except (FileNotFoundError, ValueError, OSError) as e:
        LOG.warning("recent_subtopics.json unreadable (%s); starting empty", e)
        return []


def write_recent_subtopics(history: List[Dict[str, Any]]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    trimmed = history[-SUBTOPIC_HISTORY_KEEP:]
    with open(RECENT_SUBTOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump({"history": trimmed}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bump rotation state after PR merge")
    p.add_argument("--pr-body", required=True,
                   help="PR body をダンプしたファイルパス")
    p.add_argument("--pr-title", default="",
                   help="PR title（記録用）")
    p.add_argument("--merged-date", default="",
                   help="マージ日 YYYY-MM-DD (JST)。省略で今日")
    return p.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    if not os.path.exists(args.pr_body):
        LOG.error("PR body file not found: %s", args.pr_body)
        return 2
    with open(args.pr_body, "r", encoding="utf-8") as f:
        body = f.read()

    fields = parse_pr_body(body)
    LOG.info("Parsed fields: %s", fields)
    category = fields.get("category", "")
    subtopic = fields.get("subtopic", "")
    candidate = fields.get("candidate", "")

    if not category or not subtopic:
        LOG.error("PR body missing category or subtopic. Skipping state update.")
        return 0  # 失敗ではなく no-op

    if args.merged_date:
        merged_date = args.merged_date
    else:
        merged_date = datetime.now(JST).strftime("%Y-%m-%d")

    # 1. recent_subtopics に追記
    history = read_recent_subtopics()
    history.append({
        "date": merged_date,
        "category": category,
        "subtopic": subtopic,
        "candidate": candidate,
        "title": args.pr_title.strip(),
    })
    write_recent_subtopics(history)
    LOG.info("recent_subtopics updated, history length=%d (kept %d).",
             len(history), min(len(history), SUBTOPIC_HISTORY_KEEP))

    # 2. rotation_index 更新
    #    金曜整備（subtopic ∈ {道路交通法, 新技術新TEC情報, 保険}）なら friday_seibi++
    #    日曜アドホック（category ∈ {AI・自動化, 対馬ライフ}）なら sunday_adhoc++
    rotation = read_rotation_index()
    bumped = False
    if category == "整備の現場" and subtopic in (
        "道路交通法", "新技術新TEC情報", "保険",
    ):
        rotation["friday_seibi"] = (rotation["friday_seibi"] + 1) % FRIDAY_ROTATION_LEN
        bumped = True
        LOG.info("friday_seibi advanced to %d", rotation["friday_seibi"])
    elif category in ("AI・自動化", "対馬ライフ"):
        rotation["sunday_adhoc"] = (rotation["sunday_adhoc"] + 1) % SUNDAY_ROTATION_LEN
        bumped = True
        LOG.info("sunday_adhoc advanced to %d", rotation["sunday_adhoc"])
    else:
        LOG.info("No rotation advance for category=%s subtopic=%s",
                 category, subtopic)

    write_rotation_index(rotation)
    LOG.info("rotation_index written: %s (bumped=%s)", rotation, bumped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
