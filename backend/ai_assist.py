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


def _make_client():
    if settings.use_bedrock:
        from anthropic import AnthropicBedrock
        if settings.aws_bearer_token_bedrock:
            # Bearer-token auth (Claude Code / SSO style)
            return AnthropicBedrock(
                aws_region=settings.region,
                aws_access_key=None,
                aws_secret_key=None,
                aws_session_token=None,
                base_url=f"https://bedrock-runtime.{settings.region}.amazonaws.com",
                default_headers={
                    "Authorization": f"Bearer {settings.aws_bearer_token_bedrock}"
                },
            )
        # IAM key/secret auth
        return AnthropicBedrock(
            aws_access_key=settings.aws_access_key_id,
            aws_secret_key=settings.aws_secret_access_key,
            aws_region=settings.region,
        )
    from anthropic import Anthropic
    return Anthropic(api_key=settings.anthropic_api_key)


def assist_with_claude(prompt: str) -> dict:
    client = _make_client()
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
    if settings.ai_enabled:
        try:
            return assist_with_claude(prompt), "claude", ""
        except Exception as exc:
            return (
                assist_with_fallback(prompt),
                "fallback",
                f"Claude unavailable ({exc.__class__.__name__}); used local extraction.",
            )
    return (
        assist_with_fallback(prompt),
        "fallback",
        "No AI credentials configured; used local keyword extraction.",
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
    client = _make_client()
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
    if settings.ai_enabled:
        try:
            return contract_with_claude(prompt), "claude", ""
        except Exception as exc:
            return (
                contract_with_fallback(prompt),
                "fallback",
                f"Claude unavailable ({exc.__class__.__name__}); inferred schema locally.",
            )
    result = contract_with_fallback(prompt)
    note = "No AI credentials configured; inferred schema locally."
    if not result["schema_fields"]:
        note += " Tip: paste a CSV header row or a JSON sample to auto-detect fields."
    return result, "fallback", note


# ── Improve description ───────────────────────────────────────────────────────

def improve_description(name: str, domain: str, description: str) -> tuple[str, str]:
    """Returns (improved_text, note)."""
    prompt = f"Name: {name}\nDomain: {domain}\nDescription: {description}"
    if settings.ai_enabled:
        try:
            client = _make_client()
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=300,
                system=(
                    "You are a data catalog editor. Rewrite the given data product description "
                    "to be professional, clear and 2-3 sentences. Preserve all factual details. "
                    "Return only the improved description text with no commentary or quotes."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            return text, ""
        except Exception as exc:
            pass
    # fallback: capitalise + ensure ends with period
    d = description.strip()
    if d and not d[0].isupper():
        d = d[0].upper() + d[1:]
    if d and not d.endswith("."):
        d += "."
    return d, "AI unavailable; minor formatting applied."


# ── Suggest sources ───────────────────────────────────────────────────────────

_DOMAIN_SOURCES = {
    "finance": ["SAP S/4HANA", "Oracle Financials", "Workday", "Anaplan"],
    "sales": ["Salesforce CRM", "SAP SD", "HubSpot", "Microsoft Dynamics"],
    "marketing": ["Google Analytics", "Salesforce Marketing Cloud", "HubSpot", "Adobe Analytics"],
    "supply chain": ["SAP SCM", "Oracle SCM", "Blue Yonder", "Kinaxis"],
    "hr": ["Workday HCM", "SAP SuccessFactors", "ADP", "BambooHR"],
    "manufacturing": ["SAP PP", "Siemens MES", "Rockwell Automation", "OSIsoft PI"],
}

def suggest_sources(name: str, domain: str, description: str) -> tuple[list, str]:
    prompt = f"Data product name: {name}\nDomain: {domain}\nDescription: {description}\nList 4-6 likely source systems as a JSON array of short strings."
    if settings.ai_enabled:
        try:
            client = _make_client()
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=200,
                system="Return ONLY a JSON array of source system name strings. No prose.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                suggestions = json.loads(m.group(0))
                return [str(s).strip() for s in suggestions if s], ""
        except Exception:
            pass
    # fallback
    lower = (domain + " " + description).lower()
    for key, sources in _DOMAIN_SOURCES.items():
        if key in lower:
            return sources, "AI unavailable; domain-based suggestions used."
    return ["SAP", "Salesforce", "Snowflake", "Oracle"], "AI unavailable; generic suggestions used."


# ── Suggest tags ─────────────────────────────────────────────────────────────

def suggest_tags(name: str, domain: str, description: str, source_systems: str) -> tuple[list, str]:
    prompt = (
        f"Data product name: {name}\nDomain: {domain}\n"
        f"Description: {description}\nSources: {source_systems}\n"
        "Suggest 6-8 lowercase tags as a JSON array."
    )
    if settings.ai_enabled:
        try:
            client = _make_client()
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=150,
                system="Return ONLY a JSON array of lowercase tag strings. No prose.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                suggestions = json.loads(m.group(0))
                return [str(s).strip().lower() for s in suggestions if s], ""
        except Exception:
            pass
    # fallback: derive from domain + name words
    words = re.findall(r"[a-z]+", (name + " " + domain + " " + description).lower())
    stop = {"a", "an", "the", "of", "for", "and", "or", "is", "in", "to", "with", "data", "product"}
    tags = list(dict.fromkeys(w for w in words if w not in stop and len(w) > 2))[:8]
    return tags, "AI unavailable; keyword-based tags used."


# ── Natural language search ───────────────────────────────────────────────────

def search_interpret(query: str, all_products: list) -> tuple[dict, str]:
    """Returns (filters_dict, note). filters_dict keys: domains, classifications, tags, contains_pii, rerank_ids."""
    catalog_summary = "\n".join(
        f"- id={p['id']} name={p['name']!r} domain={p['domain']!r} tags={p['tags']!r} classification={p['classification']!r}"
        for p in all_products[:60]
    )
    prompt = (
        f"User query: {query}\n\nAvailable data products:\n{catalog_summary}\n\n"
        "Return a JSON object with keys:\n"
        "- domains: array of domain strings that match the query (from the catalog)\n"
        "- classifications: array of classification strings (Public/Internal/Confidential/Restricted)\n"
        "- tags: array of tag strings\n"
        "- contains_pii: true, false, or null\n"
        f"- rerank_ids: array of product ids ordered by relevance to the query (most relevant first, include all that match)\n"
    )
    if settings.ai_enabled:
        try:
            client = _make_client()
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=400,
                system="You help users search a data product catalog. Return ONLY a JSON object. No prose.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                raw = json.loads(m.group(0))
                return {
                    "domains": [str(d) for d in raw.get("domains", [])],
                    "classifications": [str(c) for c in raw.get("classifications", [])],
                    "tags": [str(t) for t in raw.get("tags", [])],
                    "contains_pii": raw.get("contains_pii"),
                    "rerank_ids": [int(i) for i in raw.get("rerank_ids", [])],
                }, ""
        except Exception as exc:
            pass
    # fallback: simple keyword matching
    lower = query.lower()
    domains = [p["domain"] for p in all_products if p["domain"] and p["domain"].lower() in lower]
    cls_match = [c for c in CLASSIFICATIONS if c.lower() in lower]
    contains_pii = True if "pii" in lower or "personal" in lower else None
    return {
        "domains": list(dict.fromkeys(domains)),
        "classifications": cls_match,
        "tags": [],
        "contains_pii": contains_pii,
        "rerank_ids": [],
    }, "AI unavailable; keyword-based search used."


# ── Chat with Vega ────────────────────────────────────────────────────────────

def chat_with_product(product: dict, contract: dict | None, message: str) -> tuple[str, str]:
    """Returns (reply, note)."""
    ctx_parts = [
        f"Name: {product['name']}",
        f"Domain: {product.get('domain', '')}",
        f"Classification: {product.get('classification', '')}",
        f"Owner: {product.get('owner_name', '')} <{product.get('owner_email', '')}>",
        f"Description: {product.get('description', '')}",
        f"Sources: {product.get('source_systems', '')}",
        f"Update frequency: {product.get('update_frequency', '')}",
        f"Output format: {product.get('output_format', '')}",
        f"SLA: {product.get('sla', '')}",
        f"Contains PII: {product.get('contains_pii', False)}",
        f"Tags: {product.get('tags', '')}",
    ]
    if contract:
        fields = contract.get("schema_fields", [])
        if fields:
            ctx_parts.append("Schema fields: " + ", ".join(f"{f['name']}({f['type']})" for f in fields[:15]))
        ctx_parts.append(f"SLO availability: {contract.get('slo_availability', '')}")
        ctx_parts.append(f"SLO freshness: {contract.get('slo_freshness', '')}")

    context = "\n".join(ctx_parts)
    system = (
        "You are Vega, an AI assistant for a data product marketplace. "
        "Answer the user's question about the following data product concisely and helpfully. "
        "If you don't know, say so honestly.\n\n"
        f"DATA PRODUCT:\n{context}"
    )
    if settings.ai_enabled:
        try:
            client = _make_client()
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": message}],
            )
            reply = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            return reply, ""
        except Exception as exc:
            pass
    # fallback: structured summary
    reply = (
        f"Here's what I know about **{product['name']}**:\n"
        f"Domain: {product.get('domain', 'N/A')} | "
        f"Updated: {product.get('update_frequency', 'N/A')} | "
        f"Format: {product.get('output_format', 'N/A')} | "
        f"SLA: {product.get('sla', 'N/A')} | "
        f"PII: {'Yes' if product.get('contains_pii') else 'No'}"
    )
    return reply, "AI unavailable; showing product metadata."


# ── Input quality check + clarifying questions ───────────────────────────────

_QUALITY_SYSTEM = """You are a data catalog quality coach helping producers register data products well.

Evaluate the provided inputs and decide if they are specific enough for a proper catalog entry.

Inputs are considered POOR/VAGUE if any of these apply:
- Name is generic, a single word, random characters, or clearly a test (e.g. "test", "data", "aaa", "product1", "xyz")
- Description is missing, too short (< 15 words), or a copy of the name
- Description is gibberish or contains only placeholder text
- Domain is missing when name/description suggest a clear one
- Source systems are missing when description implies specific sources

If inputs are poor, return a JSON object with:
{
  "ok": false,
  "questions": ["<specific question 1>", "<specific question 2>", ...],
  "message": "<one sentence explaining why clarification is needed>"
}

Ask 2-4 targeted questions. Questions should be concrete and answerable, e.g.:
- "What business function or team does this data product serve? (e.g. Sales, Finance, Supply Chain)"
- "What source systems does this data come from? (e.g. SAP, Salesforce, Oracle)"
- "What problem does this data product solve for its consumers?"
- "How often is this data updated? (e.g. daily at 6am, real-time)"

If inputs are already good enough, return:
{
  "ok": true,
  "message": "Looks good!",
  "improved": {}
}

Return ONLY the JSON object. No prose, no markdown."""


def clarify_inputs(name: str, description: str, domain: str,
                   source_systems: str, answers: str) -> tuple[bool, list, dict, str]:
    """Returns (ok, questions, improved_fields, message)."""
    # Fast local check first — if clearly gibberish, don't even call the API
    def _is_trivially_bad(s: str) -> bool:
        s = s.strip().lower()
        if not s or len(s) < 3:
            return True
        if re.match(r'^[a-z]{1,3}\d*$', s):  # "a", "bb", "abc1"
            return True
        if s in {"test", "data", "product", "hello", "foo", "bar", "temp", "xyz", "aaa", "bbb", "tbd", "n/a"}:
            return True
        return False

    trivially_bad_name = _is_trivially_bad(name)
    desc_too_short = len(description.strip().split()) < 8

    prompt_parts = [f"Name: {name}", f"Description: {description}"]
    if domain:
        prompt_parts.append(f"Domain: {domain}")
    if source_systems:
        prompt_parts.append(f"Source systems: {source_systems}")
    if answers:
        prompt_parts.append(f"Producer's additional answers: {answers}")

    user_content = "\n".join(prompt_parts)

    if settings.ai_enabled:
        try:
            client = _make_client()
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=400,
                system=_QUALITY_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                raw = json.loads(m.group(0))
                ok = bool(raw.get("ok", True))
                questions = [str(q) for q in raw.get("questions", [])]
                improved = raw.get("improved", {})
                message = str(raw.get("message", ""))
                return ok, questions, improved, message
        except Exception:
            pass

    # Fallback: simple heuristic
    if trivially_bad_name or desc_too_short:
        questions = []
        if trivially_bad_name:
            questions.append("What is the full, descriptive name of this data product? (e.g. 'Daily Sales by Dealer — SAP')")
        if desc_too_short:
            questions.append("What does this data product contain and what business problem does it solve?")
        if not domain:
            questions.append("Which business function or domain owns this data? (e.g. Finance, Sales, Supply Chain)")
        if not source_systems:
            questions.append("What source systems does this data come from? (e.g. SAP, Salesforce, Oracle)")
        return False, questions, {}, "Some inputs are too vague — a few quick answers will make this product much easier to find."

    return True, [], {}, "Looks good!"


# ── Duplicate / similar product detection ────────────────────────────────────

def find_similar_products(name: str, description: str, domain: str,
                           source_systems: str, all_products: list) -> tuple[list, str]:
    """Returns (similar_list, warning). similar_list items: {id, name, domain, reason}."""
    if not all_products:
        return [], ""

    catalog = "\n".join(
        f"id={p['id']} name={p['name']!r} domain={p['domain']!r} description={str(p.get('description',''))[:120]!r}"
        for p in all_products[:80]
    )
    prompt = (
        f"New product being registered:\nName: {name}\nDomain: {domain}\n"
        f"Description: {description}\nSources: {source_systems}\n\n"
        f"Existing catalog:\n{catalog}\n\n"
        "Return a JSON array of objects for any existing products that are similar or potentially duplicate. "
        "Each object: {\"id\": <int>, \"reason\": <short string>}. "
        "Return empty array [] if no significant overlaps."
    )
    if settings.ai_enabled:
        try:
            client = _make_client()
            msg = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=300,
                system="You detect duplicate or similar data products. Return ONLY a JSON array. No prose.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                raw = json.loads(m.group(0))
                id_map = {p["id"]: p for p in all_products}
                results = []
                for item in raw:
                    pid = int(item.get("id", 0))
                    if pid in id_map:
                        p = id_map[pid]
                        results.append({"id": pid, "name": p["name"], "domain": p.get("domain", ""), "reason": item.get("reason", "")})
                warning = f"⚠️ {len(results)} similar product(s) found — consider reusing or extending them." if results else ""
                return results, warning
        except Exception:
            pass

    # fallback: simple name/domain overlap
    name_lower = name.lower()
    domain_lower = domain.lower()
    results = []
    for p in all_products:
        score = 0
        if domain_lower and p.get("domain", "").lower() == domain_lower:
            score += 1
        pname = p.get("name", "").lower()
        common = sum(1 for w in name_lower.split() if len(w) > 3 and w in pname)
        score += common
        if score >= 2:
            results.append({"id": p["id"], "name": p["name"], "domain": p.get("domain", ""), "reason": "Similar name/domain"})
    warning = f"⚠️ {len(results)} similar product(s) found." if results else ""
    return results, warning
