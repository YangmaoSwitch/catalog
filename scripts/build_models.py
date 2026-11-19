#!/usr/bin/env python3
"""Build dist/models.json: free models and where they can be used for free.

Sources
* OpenRouter public model list (https://openrouter.ai/api/v1/models): models whose
  prompt and completion price are both 0, with OpenRouter's own metadata.
* `api.free_models` of the providers in this catalog (names only).
"""
import datetime as dt
import json
import pathlib
import sys
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENROUTER = "https://openrouter.ai/api/v1/models"


def openrouter_models() -> list[dict]:
    req = urllib.request.Request(OPENROUTER, headers={"User-Agent": "YangmaoSwitch-catalog"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))["data"]
    out = []
    for m in data:
        p = m.get("pricing") or {}
        try:
            free = float(p.get("prompt", 1)) == 0 and float(p.get("completion", 1)) == 0
        except ValueError:
            free = False
        arch = m.get("architecture") or {}
        if not free or m["id"].startswith("openrouter/") or any(o != "text" for o in (arch.get("output_modalities") or ["text"])):
            continue
        name = m.get("name") or m["id"]
        vendor, _, short = name.partition(": ")
        if not short:
            vendor, short = m["id"].split("/")[0], name
        short = short.replace(" (free)", "").strip()
        params = m.get("supported_parameters") or []
        out.append({
            "id": m["id"],
            "name": short,
            "vendor": vendor.strip(),
            "description": (m.get("description") or "").strip(),
            "context_length": m.get("context_length"),
            "input_modalities": arch.get("input_modalities") or ["text"],
            "tools": "tools" in params,
            "reasoning": "reasoning" in params or bool(m.get("reasoning")),
            "created": dt.datetime.fromtimestamp(m["created"], dt.timezone.utc).date().isoformat() if m.get("created") else None,
            "hugging_face_id": m.get("hugging_face_id") or None,
            "description_source": "OpenRouter",
            "offers": [{"provider": "openrouter", "model": m["id"]}],
        })
    return out


def catalog_models() -> list[dict]:
    out = []
    for path in sorted((ROOT / "providers").glob("*.yaml")):
        p = yaml.safe_load(path.read_text(encoding="utf-8"))
        if p.get("status") == "delisted":
            continue
        for name in (p.get("api") or {}).get("free_models", []):
            out.append({
                "id": f"{p['id']}:{name}",
                "name": name,
                "vendor": None,
                "description": "",
                "context_length": None,
                "input_modalities": ["text"],
                "tools": None,
                "reasoning": None,
                "created": None,
                "hugging_face_id": None,
                "description_source": None,
                "offers": [{"provider": p["id"], "model": name}],
            })
    return out


def main() -> int:
    models = catalog_models()
    try:
        models = openrouter_models() + models
    except Exception as e:  # keep building with catalog data if OpenRouter is unreachable
        print(f"warning: OpenRouter model list unavailable: {e}", file=sys.stderr)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = {"version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "count": len(models), "models": models}
    (dist / "models.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ok: {len(models)} models -> dist/models.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
