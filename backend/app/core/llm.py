from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import requests

from ..config import settings


class LLMError(RuntimeError):
    pass


def is_enabled() -> bool:
    return bool(settings.openai_api_key)


def _request(messages: list[dict[str, Any]], temperature: float = 0.2) -> str:
    last_error: LLMError | None = None
    try:
        return _request_responses(messages, temperature=temperature)
    except LLMError as exc:
        last_error = exc
    try:
        return _request_chat_completions(messages, temperature=temperature)
    except LLMError as exc:
        last_error = exc
    raise last_error or LLMError("OpenAI API request failed")


def _request_responses(messages: list[dict[str, Any]], temperature: float = 0.2) -> str:
    if not is_enabled():
        raise LLMError("OPENAI_API_KEY is not configured")
    instructions = []
    inputs: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content")
        if role == "system" and isinstance(content, str):
            instructions.append(content)
            continue
        inputs.append(
            {
                "role": role,
                "content": _responses_content(content),
            }
        )
    response = requests.post(
        f"{settings.openai_base_url}/responses",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_model,
            "temperature": temperature,
            "instructions": "\n\n".join(item for item in instructions if item.strip()) or None,
            "input": inputs,
        },
        timeout=settings.openai_timeout_seconds,
    )
    if not response.ok:
        raise LLMError(f"OpenAI API error: {response.status_code} {response.text[:200]}")
    payload = response.json()
    return _extract_responses_text(payload)


def _request_chat_completions(messages: list[dict[str, Any]], temperature: float = 0.2) -> str:
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
        timeout=settings.openai_timeout_seconds,
    )
    if not response.ok:
        raise LLMError(f"OpenAI API error: {response.status_code} {response.text[:200]}")
    payload = response.json()
    return payload["choices"][0]["message"]["content"]


def _responses_content(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    blocks: list[dict[str, Any]] = []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            blocks.append({"type": "input_text", "text": str(item.get("text") or "")})
            continue
        if item_type == "image_url":
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                block = {"type": "input_image", "image_url": str(image_url.get("url") or "")}
                if image_url.get("detail"):
                    block["detail"] = image_url["detail"]
                blocks.append(block)
            elif image_url:
                blocks.append({"type": "input_image", "image_url": str(image_url)})
    return blocks or [{"type": "input_text", "text": ""}]


def _extract_responses_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            text = ""
            if content.get("type") == "output_text":
                text = str(content.get("text") or "")
            elif content.get("type") == "text":
                text = str(content.get("text") or "")
            if text:
                parts.append(text)
    if parts:
        return "\n".join(parts).strip()
    for key in ["output_text", "text"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise LLMError("Responses API did not return text output")


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


def extract_image_text(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(suffix, "application/octet-stream")
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "请只提取图片中真实可见的文字内容，按阅读顺序输出纯文本。"
        "不要解释，不要总结，不要补写看不清的内容。"
        "如果图片里存在标题、表格、列表或多段文本，请尽量保留层次和换行。"
        "如果图片中几乎没有可辨识文字，就返回空字符串。"
    )
    return _request(
        [
            {"role": "system", "content": "你是严谨的 OCR 文本提取助手，只输出图片中真实可见的文字。"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{payload}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        temperature=0,
    ).strip()
