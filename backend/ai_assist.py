"""AI assistant that turns a free-text description into structured form fields.

Uses the Claude API when ANTHROPIC_API_KEY is set, and falls back to a
keyword-based heuristic so the portal stays fully functional offline.
"""
import json
import re

from config import settings
from schemas import (
    CLASSIFICATIONS,
    FIELD_TYPES,
    FORMATS,
    FREQUENCIES,
    RULE_TYPES,
)

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


# ---------------------------------------------------------------------------
# Data contract drafting
# ---------------------------------------------------------------------------
CONTRACT_SYSTEM_PROMPT = f"""You help author a data contract for a data product.
Given a description and/or a sample of the data (CSV header row, JSON object, or
a column list), return ONLY a JSON object (no markdown, no prose) with keys:
- schema_fields: array of {{name, type, required (bool), pii (bool), description}}
  where type is one of {FIELD_TYPES}
- quality_rules: array of {{field, rule, description}} where rule is one of
  {RULE_TYPES} and field is the column name ("" for dataset-level rules)
- slo_availability: string (e.g. "99.9%")
- slo_freshness: string (e.g. "Refreshed by 6am daily")
- slo_max_latency: string (e.g. "< 200ms p95" for APIs, else "")
Infer sensible types and a not_null rule for clearly required keys/ids. Mark
fields that look like personal data (name, email, phone, address, ssn) pii=true.
Keep it concise; do not invent fields that aren't implied.
"""


def _coerce_field(raw: dict) -> dict:
    return {
        "name": str(raw.get("name", "")).strip(),
        "type": _coerce(str(raw.get("type", "string")), FIELD_TYPES, "string"),
        "required": bool(raw.get("required", False)),
        "pii": bool(raw.get("pii", False)),
        "description": str(raw.get("description", "")).strip(),
    }


def _coerce_rule(raw: dict) -> dict:
    return {
        "field": str(raw.get("field", "")).strip(),
        "rule": _coerce(str(raw.get("rule", "not_null")), RULE_TYPES, "custom"),
        "description": str(raw.get("description", "")).strip(),
    }


def _clean_contract(raw: dict) -> dict:
    fields = [_coerce_field(f) for f in raw.get("schema_fields", []) if f.get("name")]
    rules = [_coerce_rule(r) for r in raw.get("quality_rules", [])]
    return {
        "schema_fields": fields,
        "quality_rules": rules,
        "slo_availability": str(raw.get("slo_availability", "")).strip(),
        "slo_freshness": str(raw.get("slo_freshness", "")).strip(),
        "slo_max_latency": str(raw.get("slo_max_latency", "")).strip(),
    }


def contract_with_claude(prompt: str) -> dict:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1500,
        system=CONTRACT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Claude did not return JSON")
    return _clean_contract(json.loads(match.group(0)))


PII_HINTS = ["name", "email", "phone", "address", "ssn", "dob", "birth", "zip", "postal"]
_INT_RE = re.compile(r"^-?\d+$")
_NUM_RE = re.compile(r"^-?\d+\.\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _infer_type(sample: str) -> str:
    s = (sample or "").strip()
    if not s:
        return "string"
    if s.lower() in {"true", "false"}:
        return "boolean"
    if _INT_RE.match(s):
        return "integer"
    if _NUM_RE.match(s):
        return "number"
    if _DATE_RE.match(s):
        return "timestamp" if len(s) > 10 else "date"
    return "string"


def contract_with_fallback(prompt: str) -> dict:
    """Best-effort schema inference from a CSV header, JSON object, or column list."""
    text = prompt.strip()
    columns = []  # list of (name, sample_value)

    # 1) Try JSON object -> use keys (and value types).
    try:
        obj = json.loads(text)
        if isinstance(obj, list) and obj:
            obj = obj[0]
        if isinstance(obj, dict):
            for k, v in obj.items():
                columns.append((str(k), "" if v is None else str(v)))
    except (ValueError, TypeError):
        pass

    # 2) Try CSV: a header line, optionally with a data row beneath it.
    if not columns:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        comma_lines = [ln for ln in lines if "," in ln]
        if comma_lines:
            header = comma_lines[0]
            names = [c.strip().strip('"') for c in header.split(",") if c.strip()]
            sample_row = comma_lines[1].split(",") if len(comma_lines) > 1 else []
            for i, name in enumerate(names):
                sample = sample_row[i].strip().strip('"') if i < len(sample_row) else ""
                columns.append((name, sample))

    fields = []
    for name, sample in columns:
        lname = name.lower()
        fields.append(_coerce_field({
            "name": name,
            "type": _infer_type(sample),
            "required": lname in {"id", "key"} or lname.endswith("_id"),
            "pii": any(h in lname for h in PII_HINTS),
            "description": "",
        }))

    # Dataset/field-level quality rules.
    rules = []
    for f in fields:
        if f["required"]:
            rules.append(_coerce_rule({
                "field": f["name"], "rule": "not_null",
                "description": "Required key must not be null.",
            }))
        if f["name"].lower() in {"id", "key"} or f["name"].lower().endswith("_id"):
            rules.append(_coerce_rule({
                "field": f["name"], "rule": "unique",
                "description": "Identifier should be unique.",
            }))

    # SLOs inferred from wording: pick the comma/period/newline-delimited clause
    # that mentions freshness, ignoring an availability percentage clause.
    slo_freshness = ""
    for clause in re.split(r"[,.\n]", text):
        c = clause.strip()
        if re.search(r"refresh|updated|delivered|available by", c, re.IGNORECASE) \
                and "%" not in c:
            slo_freshness = c[0].upper() + c[1:] if c else ""
            break
    avail = re.search(r"\d{2,3}(?:\.\d+)?\s*%", text)

    return _clean_contract({
        "schema_fields": fields,
        "quality_rules": rules,
        "slo_availability": avail.group(0) if avail else "",
        "slo_freshness": slo_freshness,
        "slo_max_latency": "",
    })


def generate_contract(prompt: str):
    """Returns (contract, source, note)."""
    if settings.anthropic_api_key:
        try:
            return contract_with_claude(prompt), "claude", ""
        except Exception as exc:
            return (
                contract_with_fallback(prompt),
                "fallback",
                f"Claude unavailable ({exc.__class__.__name__}); inferred schema locally.",
            )
    result = contract_with_fallback(prompt)
    note = "No ANTHROPIC_API_KEY configured; inferred schema locally."
    if not result["schema_fields"]:
        note += " Tip: paste a CSV header row or a JSON sample to auto-detect fields."
    return result, "fallback", note
