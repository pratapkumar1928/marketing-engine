"""Gemini via REST. The key travels in a header, never the URL; errors never echo it."""
import json

import requests

from engine.config import secret

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _upper_types(schema):
    """Gemini's responseSchema wants OpenAPI-style upper-case type names."""
    if isinstance(schema, dict):
        return {k: (v.upper() if k == "type" and isinstance(v, str) else _upper_types(v)) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_upper_types(x) for x in schema]
    return schema


def generate(prompt: str, schema: dict, *, model: str, http=requests) -> dict:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": _upper_types(schema)},
    }
    try:
        r = http.post(URL.format(model=model), headers={"x-goog-api-key": secret("GEMINI_API_KEY")},
                      json=body, timeout=90)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:  # noqa: BLE001 - re-raise without message, which may carry the key
        raise RuntimeError(f"gemini call failed: {type(e).__name__}") from None
    return json.loads(text)  # JSONDecodeError is a ValueError: the caller counts it as a failed attempt
