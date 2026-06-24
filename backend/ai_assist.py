"""AI assistant that turns a free-text description into structured form fields.

Uses the Claude API when ANTHROPIC_API_KEY is set, and falls back to a
keyword-based heuristic so the portal stays fully functional offline.
"""
import json
import re

from config import settings
from schemas import CLASSIFICATIONS, FORMATS, FREQUENCIES

FIELD_KEYS = [
    "name",
    "description",
    "domain",
    "owner_name",
    "owner_email",
    "classification",
    "source_systems",
    "update_frequency",
    "output_format",
    "sla",
    "contains_pii",
    "tags",
]

SYSTEM_PROMPT = f"""You help users register a data product in a catalog.
Given a free-form description, extract structured fields and return ONLY a JSON
object (no markdown, no prose) with these keys:
- name (string, short title)
- description (string, one or two sentences)
- domain (string, e.g. Sales, Finance, Manufacturing, Supply Chain)
- owner_name (string)
- owner_email (string)
- classification (one of {CLASSIFICATIONS})
- source_systems (comma-separated string)
- update_frequency (one of {FREQUENCIES})
- output_format (one of {FORMATS})
- sla (string, e.g. "99.9% availability, refreshed by 6am")
- contains_pii (boolean)
- tags (comma-separated string)
Leave a field as an empty string (or false for contains_pii) if it is not
mentioned. Do not invent owner contact details that are not stated.
"""


def _clean_fields(raw: dict) -> dict:
    fields = {}
    for key in FIELD_KEYS:
        value = raw.get(key, "")
        if key == "contains_pii":
            if isinstance(value, str):
                value = value.strip().lower() in {"true", "yes", "y", "1"}
            fields[key] = bool(value)
        else:
            fields[key] = "" if value is None else str(value).strip()
    # Constrain enum-like fields to allowed values when possible.
    fields["classification"] = _coerce(fields["classification"], CLASSIFICATIONS, "Internal")
    fields["update_frequency"] = _coerce(fields["update_frequency"], FREQUENCIES, "Daily")
    fields["output_format"] = _coerce(fields["output_format"], FORMATS, "Table")
    return fields


def _coerce(value: str, allowed: list, default: str) -> str:
    if not value:
        return default
    for option in allowed:
        if value.lower() == option.lower():
            return option
    return default


def assist_with_claude(prompt: str) -> dict:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Claude did not return JSON")
    return _clean_fields(json.loads(match.group(0)))


def assist_with_fallback(prompt: str) -> dict:
    """Best-effort keyword extraction used when no API key is configured."""
    text = prompt.strip()
    lower = text.lower()
    fields = {key: "" for key in FIELD_KEYS}
    fields["contains_pii"] = False

    # Name: first sentence / clause, trimmed.
    first = re.split(r"[.\n]", text, maxsplit=1)[0].strip()
    fields["name"] = (first[:80]).strip()
    fields["description"] = text[:500]

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if email_match:
        fields["owner_email"] = email_match.group(0)

    domain_map = {
        "sales": "Sales",
        "finance": "Finance",
        "market": "Marketing",
        "supply": "Supply Chain",
        "manufactur": "Manufacturing",
        "hr": "Human Resources",
        "dealer": "Dealer",
        "warranty": "Warranty",
    }
    for needle, value in domain_map.items():
        if needle in lower:
            fields["domain"] = value
            break

    for freq in FREQUENCIES:
        if freq.lower() in lower:
            fields["update_frequency"] = freq
            break
    else:
        if "real-time" in lower or "streaming" in lower:
            fields["update_frequency"] = "Realtime"
        else:
            fields["update_frequency"] = "Daily"

    for fmt in FORMATS:
        if fmt.lower() in lower:
            fields["output_format"] = fmt
            break
    else:
        if "api" in lower:
            fields["output_format"] = "API"
        elif "stream" in lower:
            fields["output_format"] = "Stream"
        else:
            fields["output_format"] = "Table"

    if any(w in lower for w in ["pii", "personal", "customer name", "email", "phone", "address"]):
        fields["contains_pii"] = True

    if any(w in lower for w in ["confidential", "restricted", "sensitive"]):
        fields["classification"] = "Confidential"
    elif "public" in lower:
        fields["classification"] = "Public"
    else:
        fields["classification"] = "Internal"

    # Source systems: look for "from X" or "source: X".
    src = re.search(r"(?:from|source[s]?:?)\s+([A-Za-z0-9 ,/_-]{2,60})", text, re.IGNORECASE)
    if src:
        fields["source_systems"] = src.group(1).strip().rstrip(".")

    return _clean_fields(fields)


def generate_fields(prompt: str):
    """Returns (fields, source, note)."""
    if settings.anthropic_api_key:
        try:
            return assist_with_claude(prompt), "claude", ""
        except Exception as exc:  # fall back gracefully on any API error
            return (
                assist_with_fallback(prompt),
                "fallback",
                f"Claude unavailable ({exc.__class__.__name__}); used local extraction.",
            )
    return (
        assist_with_fallback(prompt),
        "fallback",
        "No ANTHROPIC_API_KEY configured; used local keyword extraction.",
    )
