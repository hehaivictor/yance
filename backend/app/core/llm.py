from __future__ import annotations

import json
from typing import Any

import requests

from ..config import settings


class LLMError(RuntimeError):
    pass


def is_enabled() -> bool:
    return bool(settings.openai_api_key)


def _request(messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    if not is_enabled():
        raise LLMError("OPENAI_API_KEY is not configured")
    response = requests.post(
        f"{settings.openai_base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_model,
            "temperature": temperature,
            "messages": messages,
        },
        timeout=60,
    )
    if not response.ok:
        raise LLMError(f"OpenAI API error: {response.status_code} {response.text[:200]}")
    payload = response.json()
    return payload["choices"][0]["message"]["content"]


def complete_text(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    return _request(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )


def complete_json(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict[str, Any]:
    raw = complete_text(system_prompt, user_prompt, temperature=temperature)
    if raw.strip().startswith("```"):
        raw = raw.strip().strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise LLMError("Model did not return JSON")
    return json.loads(raw[start : end + 1])
