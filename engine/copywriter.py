"""AI-written hooks/captions, gated by rule checks and an LLM claim checker. Two attempts, then CopyRejected."""
import difflib
import re
import unicodedata
from pathlib import Path

import yaml

from engine.recipes import pool
from engine.types import Copy, CopyRejected, Plan

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
HOOK_MAX, CAPTION_MAX, LINE_MAX = 60, 300, 70
TAGS_MIN, TAGS_MAX = 3, 5
DUP_RATIO = 0.8
GLOBAL_BANNED = ["download now", "link in bio", "click the link", "buy now", "limited time",
                 "fuck", "shit", "bitch", "damn", "ass", "crap"]

COPY_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "key": {"type": "string"}, "text": {"type": "string"}}, "required": ["key", "text"]}},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hook", "lines", "caption", "hashtags"],
}
CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {"type": "object", "properties": {
        "text": {"type": "string"}, "supported": {"type": "boolean"}}, "required": ["text", "supported"]}}},
    "required": ["claims"],
}


def _tag(t: str) -> str:
    return "#" + t.strip().lstrip("#").lower()


def _read(app: dict, rel: str, default=""):
    p = Path(app["dir"]) / rel
    return p.read_text(encoding="utf-8") if p.is_file() else default


def _hashtags(app: dict) -> list[str]:
    return [_tag(t) for t in (yaml.safe_load(_read(app, "copy/hashtags.yaml", "[]")) or [])]


def _facts(app: dict) -> list[str]:
    return [f["text"] for f in pool(app, "fact")]


def line_keys(recipe: dict) -> list[str]:
    return [b["text"].split(":", 1)[1] for b in recipe["beats"] if b.get("text", "").startswith("line:")]


def describe_content(kind: str, item: dict) -> str:
    if kind == "roast":
        return (f"Roast line (shown verbatim, do not repeat it): persona {item.get('persona')}, "
                f"headline \"{item.get('headline')}\", subtitle \"{item.get('subtitle')}\"")
    if kind == "clip":
        return f"Video clip: {item.get('desc', item.get('id'))}"
    return f"Fact: {item.get('text')}"


def _all_text(c: Copy) -> str:
    return "\n".join([c.hook, *[v for k, v in c.texts.items() if k != "hook"], c.caption])


_ZERO_WIDTH = dict.fromkeys(map(ord, "­​‌‍‎‏⁠﻿"))
# Latin look-alikes that NFKC leaves alone (Cyrillic / Greek).
_CONFUSABLE = str.maketrans("аеорсухіјѕԁоαεορντκ", "aeopcyxijsdoaeopvtk")
_FORMATTING = re.compile(r"(^|\n)\s*#{1,6}\s|[<>]|```")


def normalize(text: str) -> str:
    """Lowercase, fold look-alikes and invisible chars, collapse every non-word run to one space."""
    t = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).lower().translate(_CONFUSABLE)
    return " " + re.sub(r"[\W_]+", " ", t).strip() + " "


def validate_copy(c: Copy, app: dict, recent_captions: list[str]) -> list[str]:
    reasons = []
    if len(c.hook) > HOOK_MAX:
        reasons.append(f"hook longer than {HOOK_MAX} chars")
    if len(c.caption) > CAPTION_MAX:
        reasons.append(f"caption longer than {CAPTION_MAX} chars")
    for k, v in c.texts.items():
        if k != "hook" and len(v) > LINE_MAX:
            reasons.append(f"line '{k}' longer than {LINE_MAX} chars")
    allowed = set(_hashtags(app))
    tags = [_tag(t) for t in c.hashtags]
    if not TAGS_MIN <= len(tags) <= TAGS_MAX:
        reasons.append(f"need {TAGS_MIN}-{TAGS_MAX} hashtags, got {len(tags)}")
    bad = [t for t in tags if t not in allowed]
    if bad:
        reasons.append(f"hashtag not in allowed list: {', '.join(bad)}")
    raw = _all_text(c)
    if _FORMATTING.search(raw):
        reasons.append("formatting not allowed (markdown headings, < >, code fences)")
    text = normalize(raw)
    for word in GLOBAL_BANNED + [str(w) for w in app.get("banned", [])]:
        phrase = normalize(word).strip()
        if phrase and f" {phrase} " in text:
            reasons.append(f"banned phrase: {word.lower()}")
    for old in recent_captions:
        if difflib.SequenceMatcher(None, c.caption.lower(), str(old).lower()).ratio() >= DUP_RATIO:
            reasons.append("caption is a near duplicate of a recent post")
            break
    return reasons


def _fence(text: str) -> str:
    """Copy is untrusted data for the checker: one line, no tags or headings that could pose as instructions."""
    t = text.replace("<", "‹").replace(">", "›").replace("#", "＃")
    return "<copy>" + " / ".join(x.strip() for x in t.splitlines() if x.strip()) + "</copy>"


def check_claims(c: Copy, facts: list[str], llm) -> list[str]:
    """Unsupported claims. Any malformed checker reply raises (fail closed: the attempt counts as failed)."""
    prompt = (PROMPTS / "claim_checker.md").read_text(encoding="utf-8").format_map(
        {"facts": "\n".join(f"- {f}" for f in facts), "copy": _fence(_all_text(c))})
    claims = llm(prompt, CLAIMS_SCHEMA)["claims"]
    if not isinstance(claims, list):
        raise ValueError("claims is not a list")
    out = []
    for cl in claims:
        if not isinstance(cl, dict) or not isinstance(cl.get("supported"), bool):
            raise ValueError("malformed claim entry")
        if cl["supported"] is not True:
            out.append(str(cl.get("text", "")))
    return out


def _parse(raw: dict, keys: list[str]) -> tuple[Copy, list[str]]:
    lines = {str(x.get("key")): str(x.get("text", "")) for x in raw.get("lines", []) if isinstance(x, dict)}
    missing = [k for k in keys if not lines.get(k)]
    hook = str(raw.get("hook", "")).strip()
    texts = {"hook": hook, **{k: lines[k] for k in keys if k in lines}}
    c = Copy(hook=hook, texts=texts, caption=str(raw.get("caption", "")).strip(),
             hashtags=[str(t) for t in raw.get("hashtags", [])])
    return c, [f"missing line '{k}'" for k in missing] + ([] if hook else ["empty hook"])


def write_copy(plan: Plan, recipe: dict, app: dict, content: dict, llm, recent_captions: list[str]) -> Copy:
    keys = line_keys(recipe)
    facts = _facts(app)
    base = {
        "app_name": app.get("name", app["slug"]),
        "facts": "\n".join(f"- {f}" for f in facts),
        "style": _read(app, "copy/style.md"),
        "beats": "\n".join(f"- {b['block']} ({b['dur']}s){' text=' + b['text'] if b.get('text') else ''}"
                           for b in recipe["beats"]),
        "content": describe_content(recipe["content"], content),
        "line_keys": ", ".join(keys) or "(none)",
        "hashtags": ", ".join(_hashtags(app)),
    }
    template = (PROMPTS / "copywriter.md").read_text(encoding="utf-8")
    reasons: list[str] = []
    for _attempt in range(2):
        feedback = ("\n## Your previous attempt was rejected for these reasons, fix them:\n"
                    + "\n".join(f"- {r}" for r in reasons)) if reasons else ""
        prompt = template.format_map({**base, "feedback": feedback})
        try:
            c, reasons = _parse(llm(prompt, COPY_SCHEMA), keys)
            reasons += validate_copy(c, app, recent_captions)
            if not reasons:
                reasons = [f"unsupported claim: {x}" for x in check_claims(c, facts, llm)]
        except Exception as e:  # noqa: BLE001 - malformed output or provider error = failed attempt
            reasons = [f"llm output unusable: {type(e).__name__}"]
        if not reasons:
            return c
    raise CopyRejected("; ".join(reasons))
