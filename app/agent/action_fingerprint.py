import json
from typing import Any, Mapping


def action_fingerprint(action: Mapping[str, Any]) -> str:

    payload = {k: action[k] for k in sorted(action.keys())}

    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
