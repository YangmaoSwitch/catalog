#!/usr/bin/env python3
"""Validate providers/*.yaml against the schema and build dist/catalog.json."""
import datetime as dt
import json
import pathlib
import sys

import jsonschema
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "provider.schema.json").read_text(encoding="utf-8"))
validator = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())


def main() -> int:
    errors = 0
    providers = []
    for path in sorted((ROOT / "providers").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        # YAML may parse dates; normalise to strings before validation.
        if isinstance(data.get("last_verified"), (dt.date, dt.datetime)):
            data["last_verified"] = data["last_verified"].isoformat()
        problems = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if data.get("id") != path.stem:
            problems.append(jsonschema.ValidationError(f"id '{data.get('id')}' must match file name '{path.stem}'"))
        if data.get("api_usable") and not data.get("api"):
            problems.append(jsonschema.ValidationError("api_usable entries need an 'api' block"))
        for p in problems:
            loc = "/".join(str(x) for x in p.path) or "<root>"
            print(f"{path.name}: {loc}: {p.message}", file=sys.stderr)
        errors += len(problems)
        providers.append(data)

    if errors:
        print(f"{errors} error(s)", file=sys.stderr)
        return 1

    # Only platforms usable through the app are listed; others only as a paid promotion (`promoted: true`).
    listed = [p for p in providers if p["status"] != "delisted" and (p.get("api_usable") or p.get("promoted"))]
    # an announced end date that has passed marks the offer as ended (kept and labelled, not removed)
    today = dt.date.today().isoformat()
    for p in listed:
        if p.get("ends") and p["ends"] < today and not p.get("ended"):
            p["ended"] = p["ends"]
    out = {
        "version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "count": len(listed),
        "providers": listed,
    }
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "catalog.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ok: {len(listed)} providers -> dist/catalog.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
