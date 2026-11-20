#!/usr/bin/env python3
"""Build dist/models.json (v2): the model list of every platform in the catalog.

For each platform it records which models it serves, whether each one is free,
counted against the platform's free quota/credits, or paid, and the list price.
The same model on different platforms is merged into one entry for the app's
model square.

Sources, per platform (see `api` in providers/*.yaml)
* OpenRouter: its public model list (pricing included).
* `api.modelsdev`: the platform's list in models.dev (https://models.dev, MIT),
  with prices and capabilities.
* `api.models_url`: a public model list endpoint that needs no key.
* `api.models`: models entered by hand.
Access of a model on a platform
* free:  listed in `api.free_models`, or its price is 0;
* quota: listed in `api.quota_models`, or the platform default `api.models_access`
         is "quota" (calls are covered by the free quota or credits);
* paid:  otherwise.
"""
import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENROUTER = "https://openrouter.ai/api/v1/models"
MODELSDEV = "https://models.dev/api.json"
RANKINGS = "https://openrouter.ai/rankings"
PUBLISHED = "https://raw.githubusercontent.com/YangmaoSwitch/catalog/dist/models.json"
RANK = {"free": 0, "quota": 1, "paid": 2}
# Public lists also contain embedding, safety, speech and image models; only chat models are kept.
NON_CHAT = re.compile(r"embed|rerank|clip|retriever|detector|guard|safety|riva-|image|bge-|starcoder|tts|lyria|live|ocr|translate|whisper|asr", re.I)


def model_key(model_id: str) -> str:
    """Normalized model name used to match the same model across platforms."""
    s = model_id.split("/")[-1].split(":")[0].lower()
    s = re.sub(r"[\s_.]+", "-", s)
    s = re.sub(r"-(free|ga)$", "", s)
    s = re.sub(r"-(free|ga)(?=-\d{6}$)", "", s)
    s = re.sub(r"-\d{6}$", "", s)  # date stamp such as doubao-seed-2-1-pro-260628
    return s


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "YangmaoSwitch-catalog"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def price(inp, out) -> dict | None:
    """USD per million tokens."""
    try:
        return {"input": round(float(inp), 4), "output": round(float(out), 4)}
    except (TypeError, ValueError):
        return None


def meta(**kw) -> dict:
    m = {"name": None, "vendor": None, "description": "", "context_length": None, "input_modalities": ["text"],
         "tools": None, "reasoning": None, "created": None, "hugging_face_id": None, "open_weights": None, "description_source": None}
    m.update({k: v for k, v in kw.items() if v is not None})
    return m


def from_openrouter() -> list[dict]:
    out = []
    for m in fetch_json(OPENROUTER)["data"]:
        arch = m.get("architecture") or {}
        if m["id"].startswith("openrouter/") or any(o != "text" for o in (arch.get("output_modalities") or ["text"])):
            continue
        p = m.get("pricing") or {}
        pr = price(float(p.get("prompt", 0) or 0) * 1e6, float(p.get("completion", 0) or 0) * 1e6)
        name = m.get("name") or m["id"]
        vendor, _, short = name.partition(": ")
        if not short:
            vendor, short = m["id"].split("/")[0], name
        params = m.get("supported_parameters") or []
        out.append({
            "model": m["id"],
            "price": pr,
            "free": bool(pr) and pr["input"] == 0 and pr["output"] == 0,
            "meta": meta(
                name=short.replace(" (free)", "").strip(), vendor=vendor.strip(), description=(m.get("description") or "").strip(),
                context_length=m.get("context_length"), input_modalities=arch.get("input_modalities") or ["text"],
                tools="tools" in params, reasoning="reasoning" in params or bool(m.get("reasoning")),
                created=dt.datetime.fromtimestamp(m["created"], dt.timezone.utc).date().isoformat() if m.get("created") else None,
                hugging_face_id=m.get("hugging_face_id") or None, description_source="OpenRouter"),
        })
    return out


def from_modelsdev(md: dict, pid: str) -> list[dict]:
    out = []
    for mid, m in (md.get(pid) or {}).get("models", {}).items():
        mod = m.get("modalities") or {}
        if (mod.get("output") or ["text"]) != ["text"] or NON_CHAT.search(mid):
            continue
        c = m.get("cost") or {}
        pr = price(c.get("input"), c.get("output")) if c else None
        canon = m.get("canonical_model_id")
        out.append({
            "model": mid,
            "key": model_key(canon) if canon else None,
            "price": pr,
            "free": bool(pr) and pr["input"] == 0 and pr["output"] == 0,
            "meta": meta(
                name=re.sub(r"\s*\(free\)$", "", m.get("name") or mid).split("/")[-1], description=(m.get("description") or "").strip(),
                context_length=(m.get("limit") or {}).get("context"), input_modalities=mod.get("input") or ["text"],
                tools=m.get("tool_call"), reasoning=m.get("reasoning"), created=m.get("release_date"), open_weights=m.get("open_weights")),
        })
    return out


def provider_models(p: dict, md: dict | None) -> list[dict]:
    """All chat models of one platform: [{model, access, price, meta, key}]."""
    api = p.get("api") or {}
    raw: list[dict] = []
    if p["id"] == "openrouter":
        raw += from_openrouter()
    live = None
    if api.get("models_url"):
        try:
            live = [m["id"] for m in fetch_json(api["models_url"])["data"] if not NON_CHAT.search(m["id"])]
        except Exception as e:  # keep building with the other sources
            print(f"warning: {p['id']} model list unavailable: {e}", file=sys.stderr)
    srcs = api.get("modelsdev") or []
    for pid in [srcs] if isinstance(srcs, str) else srcs:
        if md is not None:
            got = from_modelsdev(md, pid)
            if live is not None:  # the live list is authoritative; models.dev only adds prices and capabilities
                ids = set(live)
                got = [r for r in got if r["model"] in ids]
            raw += got
    if live is not None:
        raw += [{"model": m} for m in live]
    raw += [{"model": n} for n in api.get("models", [])] + [{"model": n} for n in api.get("free_models", [])]

    free = {model_key(n) for n in api.get("free_models", [])}
    free_re = re.compile(api["free_pattern"]) if api.get("free_pattern") else None
    quota = {model_key(n) for n in api.get("quota_models", [])}
    default = api.get("models_access", "paid" if p["id"] == "openrouter" else "quota")
    # one entry per exact model id; variants such as "x" and "x:free" / "x-free" stay separate here
    out: dict[str, dict] = {}
    for r in raw:
        k = r.get("key") or model_key(r["model"])
        acc = "free" if (r.get("free") or model_key(r["model"]) in free or k in free or (free_re and free_re.search(r["model"]))) else "quota" if (model_key(r["model"]) in quota or k in quota) else default
        cur = out.get(r["model"])
        if cur is None:
            out[r["model"]] = {"key": k, "model": r["model"], "access": acc, "price": r.get("price"), "meta": r.get("meta")}
            continue
        cur["access"] = min(cur["access"], acc, key=RANK.get)
        cur["price"] = cur["price"] or r.get("price")
        cur["meta"] = cur["meta"] or r.get("meta")
    for m in out.values():  # a free model costs nothing, whatever a source lists
        if m["access"] == "free":
            m["price"] = {"input": 0, "output": 0}
    return list(out.values())


def openrouter_usage() -> dict[str, int]:
    """Daily tokens of OpenRouter's most used models (from its public rankings page), by model key."""
    req = urllib.request.Request(RANKINGS, headers={"User-Agent": "Mozilla/5.0 (YangmaoSwitch-catalog)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        page = r.read().decode("utf-8", "replace").replace('\\"', '"')
    out: dict[str, int] = {}
    for o in re.findall(r"\{[^{}]*model_permaslug[^{}]*\}", page):
        slug = re.search(r'"model_permaslug":"([^"]+)"', o)
        tok = [int(x) for x in re.findall(r'"total_(?:prompt|completion)_tokens":(\d+)', o)]
        if slug and tok:
            k = model_key(re.sub(r"-\d{8}$", "", slug.group(1)))
            out[k] = out.get(k, 0) + sum(tok)
    return out


def previous() -> dict:
    """The last published models.json, to keep the date each free offer first appeared."""
    try:
        if os.environ.get("PREVIOUS_FILE"):
            return json.loads(pathlib.Path(os.environ["PREVIOUS_FILE"]).read_text(encoding="utf-8"))
        return fetch_json(PUBLISHED)
    except Exception as e:
        print(f"warning: previous models.json unavailable: {e}", file=sys.stderr)
        return {}


MODELSCOPE_API = "https://modelscope.cn/api/v1/models/"
# Hugging Face organisations whose ModelScope mirror uses another name
MS_ORGS = {"zai-org": "ZhipuAI", "thudm": "ZhipuAI", "z-ai": "ZhipuAI", "minimaxai": "MiniMax", "minimax": "MiniMax", "moonshotai": "moonshotai",
           "deepseek": "deepseek-ai", "qwen": "Qwen", "stepfun": "stepfun-ai", "xiaomimimo": "XiaomiMiMo", "baidu": "PaddlePaddle"}


def downloads(models: list[dict], prev: dict) -> dict[str, int]:
    """Open-weight downloads on ModelScope (reachable from mainland China and from CI), by merged model key.
    Candidates are the model's Hugging Face id and the repo-style ids providers use (org/Name)."""
    old = {m["id"]: m.get("downloads") for m in prev.get("models", []) if m.get("downloads")}
    cands: dict[str, list[str]] = {}
    for m in models:
        ids = [m.get("hugging_face_id")] + [o["model"] for o in m["offers"]]
        out = []
        for i in ids:
            if not i or i.count("/") != 1 or i.startswith("@"):
                continue
            org, name = i.split("/")
            name = name.split(":")[0]
            for o in (org, MS_ORGS.get(org.lower(), org)):
                c = f"{o}/{name}"
                if c not in out:
                    out.append(c)
        cands[m["_key"]] = out[:4]

    def one(item):
        key, ids = item
        for i in ids:
            try:
                d = fetch_json(MODELSCOPE_API + i).get("Data") or {}
                if d.get("Downloads"):
                    return key, int(d["Downloads"])
            except Exception:
                continue
        return key, 0

    from concurrent.futures import ThreadPoolExecutor
    res: dict[str, int] = {}
    with ThreadPoolExecutor(8) as ex:
        for k, n in ex.map(one, [(k, v) for k, v in cands.items() if v]):
            if n:
                res[k] = n
    for m in models:  # keep the last known count when ModelScope does not answer this time
        if m["_key"] not in res and old.get(m["id"]):
            res[m["_key"]] = old[m["id"]]
    return res


def heat(m: dict, usage: dict[str, int], dls: dict[str, int]) -> float:
    """Popularity score.
    * OpenRouter daily tokens (its rankings page shows the top 20 only): 10 x log10(tokens / 1e9)
    * open-weight downloads on ModelScope: 6 x log10(downloads)
      the larger of the two counts fully, the other a quarter, so closed and open models compare
    * 2 per provider serving it for free or on a free quota, 1 per provider overall
    * 5 for models released in the last 30 days"""
    tokens = usage.get(m["_key"], 0)
    a = 10 * math.log10(tokens / 1e9) if tokens > 1e9 else 0.0
    n = dls.get(m["_key"], 0)
    b = 6 * math.log10(n) if n > 1 else 0.0
    score = max(a, b) + 0.25 * min(a, b)
    score += 2 * sum(o["access"] != "paid" for o in m["offers"]) + len(m["offers"])
    if m.get("created"):
        try:
            if (dt.date.today() - dt.date.fromisoformat(m["created"][:10])).days <= 30:
                score += 5
        except ValueError:
            pass
    return round(score, 2)


def main() -> int:
    try:  # MODELSDEV_FILE: a local copy of models.dev/api.json, for offline builds
        md = json.loads(pathlib.Path(os.environ["MODELSDEV_FILE"]).read_text(encoding="utf-8")) if os.environ.get("MODELSDEV_FILE") else fetch_json(MODELSDEV)
    except Exception as e:
        print(f"warning: models.dev unavailable: {e}", file=sys.stderr)
        md = None
    providers: dict[str, list[dict]] = {}
    product_only: set[str] = set()  # free models usable only inside the platform's own product: listed, but not on the square
    for path in sorted((ROOT / "providers").glob("*.yaml")):
        p = yaml.safe_load(path.read_text(encoding="utf-8"))
        if p.get("status") == "delisted":
            continue
        if not p.get("api_usable"):
            if not p.get("promoted"):  # not usable through the app: not listed, unless it is a paid promotion
                continue
            product_only.add(p["id"])
        try:
            providers[p["id"]] = provider_models(p, md)
        except Exception as e:
            print(f"warning: {p['id']}: {e}", file=sys.stderr)
            providers[p["id"]] = []

    # merge across platforms
    merged: dict[str, dict] = {}
    for pid, lst in providers.items():
        if pid in product_only:
            continue
        for m in lst:
            e = merged.setdefault(m["key"], {"id": m["model"], "meta": None, "offers": []})
            mm = m["meta"]
            if mm and (e["meta"] is None or (mm["description_source"] and not e["meta"]["description_source"])):
                old = e["meta"]
                e["meta"] = dict(mm)
                if old:  # keep fields only the other source has
                    for f, v in old.items():
                        if e["meta"].get(f) in (None, "", ["text"]) and v not in (None, ""):
                            e["meta"][f] = v
                if mm["description_source"]:
                    e["id"] = m["model"].split(":")[0]
            offer = {"provider": pid, "model": m["model"], "access": m["access"], "price": m["price"]}
            same = next((o for o in e["offers"] if o["provider"] == pid), None)
            if same is None:
                e["offers"].append(offer)
            elif RANK[offer["access"]] < RANK[same["access"]]:  # one offer per platform: its cheapest variant
                same.update(offer)
    models = []
    for k, e in merged.items():
        mt = e["meta"] or meta()
        e["offers"].sort(key=lambda o: (RANK[o["access"]], o["provider"]))
        if e["offers"][0]["access"] == "paid":  # the square lists models usable for free somewhere
            continue
        models.append({"id": e["id"], **mt, "name": mt["name"] or e["id"].split("/")[-1], "offers": e["offers"], "_key": k})

    # popularity
    try:
        usage = openrouter_usage()
    except Exception as ex:
        print(f"warning: OpenRouter rankings unavailable: {ex}", file=sys.stderr)
        usage = {}
    # first-seen dates of free / free-quota offers, carried over from the last published file
    prev = previous()
    today = dt.date.today().isoformat()
    baseline = prev.get("baseline") or today
    seen = {f"{o['provider']}|{o['model']}": o.get("since") for pm in prev.get("models", []) for o in pm.get("offers", []) if o.get("since")}
    try:
        dls = downloads(models, prev)
    except Exception as ex:
        print(f"warning: ModelScope downloads unavailable: {ex}", file=sys.stderr)
        dls = {}
    for m in models:
        m["heat"] = heat(m, usage, dls)
        m["downloads"] = dls.get(m["_key"]) or None
        m["openrouter_tokens_day"] = usage.get(m["_key"]) or None
        for o in m["offers"]:
            if o["access"] != "paid":
                o["since"] = seen.get(f"{o['provider']}|{o['model']}") or today
        del m["_key"]
    models.sort(key=lambda m: m["heat"], reverse=True)

    # Provider ranking: popularity of the models each one serves without charge, weighted by how lasting the
    # access is: free models x3, a free quota that renews (daily / monthly) x1, a one-time gift x0.3.
    recurring = {}
    status = {}
    for path in (ROOT / "providers").glob("*.yaml"):
        y = yaml.safe_load(path.read_text(encoding="utf-8"))
        status[y["id"]] = y.get("status")
        recurring[y["id"]] = any(q.get("period") != "one-time" and not q.get("models") for q in y.get("quotas", []))
    pscore: dict[str, float] = {}
    for m in models:
        for o in m["offers"]:
            w = {"free": 3.0, "quota": 1.0 if recurring.get(o["provider"]) else 0.3}.get(o["access"], 0)
            pscore[o["provider"]] = pscore.get(o["provider"], 0) + w * (m["heat"] or 0)

    summary = {pid: {"score": round(pscore.get(pid, 0), 1), "verified": status.get(pid) == "verified", "total": len(l), "free": sum(m["access"] == "free" for m in l), "quota": sum(m["access"] == "quota" for m in l),
                     "paid": sum(m["access"] == "paid" for m in l),
                     "models": sorted(({"model": m["model"], "access": m["access"], "price": m["price"]} for m in l), key=lambda x: (RANK[x["access"]], x["model"].lower()))}
               for pid, l in providers.items()}
    out = {
        "version": 2,
        "baseline": baseline,  # offers dated on this day were already listed when tracking started
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "sources": ["OpenRouter", "models.dev", "platform model lists", "catalog"],
        "count": len(models),
        "providers": summary,
        "models": models,
    }
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "models.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for pid, s in summary.items():
        print(f"  {pid:24} {s['total']:4} models  free {s['free']:3}  quota {s['quota']:3}  paid {s['paid']:3}")
    print(f"ok: {len(models)} models on the square ({sum(len(m['offers']) > 1 for m in models)} on several platforms) -> dist/models.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
