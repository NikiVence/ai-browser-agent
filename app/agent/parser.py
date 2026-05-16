import json
import re


def _normalize_json_fences(text: str) -> str:

    cleaned = text.replace("```json", "")
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.strip()

    for ch, repl in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u201e", '"'),
        ("\u201f", '"'),
        ("\u00ab", '"'),
        ("\u00bb", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u200b", ""),
        ("\ufeff", ""),
    ):

        cleaned = cleaned.replace(ch, repl)

    return cleaned


def _repair_action_from_fragment(cleaned: str):

    m = re.search(
        r'"action"\s*:\s*"([a-zA-Z_][a-zA-Z0-9_]*)"',
        cleaned,
    )

    if not m:

        return None

    act = m.group(1)

    out = {"action": act}

    for key in ("selector", "url", "text", "key", "query", "message", "product_name", "product"):

        km = re.search(rf'"{key}"\s*:\s*"([^"]*)"', cleaned)

        if km:

            out[key] = km.group(1)

    if re.search(r'"force"\s*:\s*true', cleaned, re.I):

        out["force"] = True

    return out


def parse_action(text: str):

    cleaned = _normalize_json_fences(text)

    decoder = json.JSONDecoder()
    start = cleaned.find("{")

    if start == -1:

        repaired = _repair_action_from_fragment(cleaned)

        if repaired:

            return repaired

        print("Parse error: no JSON object in response")
        print("RAW RESPONSE:", text)

        return None

    try:

        action, _end = decoder.raw_decode(cleaned[start:])

        return action

    except json.JSONDecodeError:

        repaired = _repair_action_from_fragment(cleaned[start:])

        if repaired:

            return repaired

        print("Parse error: invalid JSON in response")
        print("RAW RESPONSE:", text)

        return None
