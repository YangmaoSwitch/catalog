#!/usr/bin/env python3
"""Build dist/models.json: free models and every catalog platform that serves them.

Sources
* OpenRouter public model list (https://openrouter.ai/api/v1/models). Models whose
  prompt and completion price are both 0 are free; paid ones are only attached as
  extra offers to models that are free somewhere else.
* `api.free_models` of the providers in this catalog (access "free").
* `api.models` and the public `api.models_url` list of a provider (access per
  `api.models_access`, default "quota").

Models are merged across platforms by a normalized name, so one entry lists all
platforms that serve it. Each offer: {provider, model, access}, access being
free | quota | paid.
"""
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENROUTER = "https://openrouter.ai/api/v1/models"
RANK = {"free": 0, "quota": 1, "paid": 2}
# Public lists also contain embedding, safety and image models; the square only lists chat models.
NON_CHAT = re.compile(r"embed|rerank|clip|retriever|detector|guard|safety|riva-|image|bge-|starcoder", re.I)


def model_key(model_id: str) -> str:
    """Normalized model name used to match the same model across platforms."""
    s = model_id.split(":")[0] if ":" in model_id.split("/")[-1] else model_id
    s = s.split("/")[-1].lower()
    return re.sub(r"[\s_.]+", "-", s)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "YangmaoSwitch-catalog"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def bare(model_id: str, name: str | None = None) -> dict:
    return {
        "id": model_id,
        "name": name or model_id.split("/")[-1],
        "vendor": None,
        "description": "",
        "context_length": None,
        "input_modalities": ["text"],
        "tools": None,
        "reasoning": None,
        "created": None,
        "hugging_face_id": None,
        "description_source": None,
        "offers": [],
    }


def openrouter_models() -> list[dict]:
    out = []
    for m in fetch_json(OPENROUTER)["data"]:
        p = m.get("pricing") or {}
        try:
            free = float(p.get("prompt", 1)) == 0 and float(p.get("completion", 1)) == 0
        except ValueError:
            free = False
        arch = m.get("architecture") or {}
        if m["id"].startswith("openrouter/") or any(o != "text" for o in (arch.get("output_modalities") or ["text"])):
            continue
        name = m.get("name") or m["id"]
        vendor, _, short = name.partition(": ")
        if not short:
            vendor, short = m["id"].split("/")[0], name
        short = short.replace(" (free)", "").strip()
        params = m.get("supported_parameters") or []
        e = bare(m["id"], short)
        e.update({
            "vendor": vendor.strip(),
            "description": (m.get("description") or "").strip(),
            "context_length": m.get("context_length"),
            "input_modalities": arch.get("input_modalities") or ["text"],
            "tools": "tools" in params,
            "reasoning": "reasoning" in params or bool(m.get("reasoning")),
            "created": dt.datetime.fromtimestamp(m["created"], dt.timezone.utc).date().isoformat() if m.get("created") else None,
            "hugging_face_id": m.get("hugging_face_id") or None,
            "description_source": "OpenRouter",
            "offers": [{"provider": "openrouter", "model": m["id"], "access": "free" if free else "paid"}],
        })
        out.append(e)
    return out


def catalog_models() -> list[dict]:
    out = []
    for path in sorted((ROOT / "providers").glob("*.yaml")):
        p = yaml.safe_load(path.read_text(encoding="utf-8"))
        if p.get("status") == "delisted":
            continue
        api = p.get("api") or {}
        access = api.get("models_access", "quota")
        listed = [(n, "free") for n in api.get("free_models", [])] + [(n, access) for n in api.get("models", [])]
        if api.get("models_url"):
            try:
                listed += [(m["id"], access) for m in fetch_json(api["models_url"])["data"] if not NON_CHAT.search(m["id"])]
            except Exception as e:  # keep building with what we have
                print(f"warning: {p['id']} model list unavailable: {e}", file=sys.stderr)
        for name, acc in listed:
            e = bare(name)
            e["offers"] = [{"provider": p["id"], "model": name, "access": acc}]
            out.append(e)
    return out


def merge(entries: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for e in entries:
        k = model_key(e["id"])
        cur = by_key.get(k)
        if cur is None:
            by_key[k] = e
            order.append(k)
            continue
        if not cur["description_source"] and e["description_source"]:  # prefer the entry with metadata
            e["offers"], cur = cur["offers"] + e["offers"], e
            by_key[k] = cur
        else:
            cur["offers"] += e["offers"]
    out = []
    for k in order:
        e = by_key[k]
        best: dict[str, dict] = {}
        for o in e["offers"]:  # one offer per platform, the cheapest access wins
            if o["provider"] not in best or RANK[o["access"]] < RANK[best[o["provider"]]["access"]]:
                best[o["provider"]] = o
        e["offers"] = sorted(best.values(), key=lambda o: RANK[o["access"]])
        if e["offers"][0]["access"] != "paid":  # only models usable for free somewhere
            out.append(e)
    return out


def main() -> int:
    entries = []
    try:
        entries += openrouter_models()
    except Exception as e:  # keep building with catalog data if OpenRouter is unreachable
        print(f"warning: OpenRouter model list unavailable: {e}", file=sys.stderr)
    entries += catalog_models()
    models = merge(entries)
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = {"version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "count": len(models), "models": models}
    (dist / "models.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    multi = sum(1 for m in models if len(m["offers"]) > 1)
    print(f"ok: {len(models)} models ({multi} on several platforms) -> dist/models.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
