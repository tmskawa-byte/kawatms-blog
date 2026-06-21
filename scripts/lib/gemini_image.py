"""Gemini API 直叩きで画像生成。Nano Banana Pro / Nano Banana を呼ぶ。"""
from __future__ import annotations

import logging
import os
from typing import Tuple

LOG = logging.getLogger(__name__)

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
HERO_MODEL = "gemini-3-pro-image-preview"   # Nano Banana Pro（テキスト入りヒーロー画像）
H2_MODEL = "gemini-2.5-flash-image"         # Nano Banana（テキスト無し H2 挿絵）


class GeminiImageError(Exception):
    pass


def _client():
    """google-genai Client を返す。API キー未設定なら GeminiImageError。"""
    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        raise GeminiImageError(f"{GEMINI_API_KEY_ENV} not set")
    try:
        from google import genai
    except ImportError as e:
        raise GeminiImageError(f"google-genai SDK missing: {e}") from e
    return genai.Client(api_key=api_key)


def generate_hero_image(prompt: str, timeout: int = 120) -> Tuple[bytes, str]:
    """ヒーロー画像（テキスト入り）を Nano Banana Pro で生成。

    Returns: (image_bytes, mime_type)
    Raises: GeminiImageError
    """
    return _generate(HERO_MODEL, prompt, timeout)


def generate_h2_image(prompt: str, timeout: int = 120) -> Tuple[bytes, str]:
    """H2 挿絵（テキスト無し）を Nano Banana で生成。

    Returns: (image_bytes, mime_type)
    Raises: GeminiImageError
    """
    return _generate(H2_MODEL, prompt, timeout)


def _generate(model: str, prompt: str, timeout: int) -> Tuple[bytes, str]:
    client = _client()
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
                http_options=types.HttpOptions(timeout=timeout * 1000),
            ),
        )
        for cand in (response.candidates or []):
            content = cand.content
            for part in (content.parts if content else []):
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    return inline.data, inline.mime_type or "image/png"
    except GeminiImageError:
        raise
    except Exception as e:
        raise GeminiImageError(f"{model} generation failed: {e}") from e
    raise GeminiImageError(f"{model}: no image in response")
