#!/usr/bin/env python3
"""Post an auto-generated blog article to Google Business Profile.

This script is intentionally non-blocking for the article pipeline: failures are
reported as GitHub Actions warnings and exit with status 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.parse import urljoin

import requests


TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GBP_POST_ENDPOINT = (
    "https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/"
    "{location_id}/localPosts"
)
MAX_SUMMARY_LENGTH = 1500
REQUEST_TIMEOUT_SECONDS = 30


def warning(message: str) -> None:
    print(f"::warning::GBP post skipped: {message}")


def clean(value: str | None) -> str:
    return (value or "").strip()


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def normalize_media_url(hero_image: str, article_url: str) -> str:
    hero_image = clean(hero_image)
    if not hero_image or hero_image.lower() in {"none", "(none)", "null"}:
        return ""
    if hero_image.startswith(("http://", "https://")):
        return hero_image
    return urljoin(article_url, hero_image)


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    title = clean(args.title)
    description = clean(args.description)
    article_url = clean(args.url)
    summary = truncate(f"{title}\n\n{description}".strip(), MAX_SUMMARY_LENGTH)

    payload: dict[str, Any] = {
        "topicType": "STANDARD",
        "summary": summary,
        "callToAction": {
            "actionType": "LEARN_MORE",
            "url": article_url,
        },
    }

    media_url = normalize_media_url(args.hero_image, article_url)
    if media_url:
        payload["media"] = [
            {
                "mediaFormat": "PHOTO",
                "sourceUrl": media_url,
            }
        ]

    return payload


def missing_env(names: list[str]) -> list[str]:
    return [name for name in names if not clean(os.environ.get(name))]


def get_access_token() -> str | None:
    required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"]
    missing = missing_env(required)
    if missing:
        warning(f"missing required OAuth secrets: {', '.join(missing)}")
        return None

    try:
        response = requests.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
                "grant_type": "refresh_token",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        warning(f"OAuth token request failed: {exc.__class__.__name__}")
        return None

    if not response.ok:
        warning(f"OAuth token request returned HTTP {response.status_code}")
        return None

    token = response.json().get("access_token")
    if not token:
        warning("OAuth token response did not include access_token")
        return None
    return str(token)


def post_to_gbp(payload: dict[str, Any], access_token: str) -> bool:
    missing = missing_env(["GBP_ACCOUNT_ID", "GBP_LOCATION_ID"])
    if missing:
        warning(f"missing required GBP identifiers: {', '.join(missing)}")
        return False

    endpoint = GBP_POST_ENDPOINT.format(
        account_id=os.environ["GBP_ACCOUNT_ID"].strip(),
        location_id=os.environ["GBP_LOCATION_ID"].strip(),
    )

    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        warning(f"GBP API request failed: {exc.__class__.__name__}")
        return False

    if not response.ok:
        warning(f"GBP API returned HTTP {response.status_code}")
        return False

    post_name = response.json().get("name", "(name unavailable)")
    print(f"GBP local post created: {post_name}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post a blog article to Google Business Profile local posts."
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--url", required=True)
    parser.add_argument("--hero-image", default="")
    parser.add_argument("--slug", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not clean(args.url):
        warning("article URL is empty")
        return 0

    payload = build_payload(args)

    if args.dry_run:
        print("GBP dry-run payload:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    token = get_access_token()
    if not token:
        return 0

    post_to_gbp(payload, token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
