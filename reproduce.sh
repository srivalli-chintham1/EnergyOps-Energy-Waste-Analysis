#!/usr/bin/env bash
# Step 10: regenerate twice with the same seed and compare row counts + SHA-256 checksums.
set -euo pipefail
cd "$(dirname "$0")"
ARGS="${@:---seed 20261022}"
rm -rf /tmp/repro_a /tmp/repro_b
python3 generate.py $ARGS --out /tmp/repro_a > /dev/null
python3 generate.py $ARGS --out /tmp/repro_b > /dev/null
python3 - <<'PY'
import json
a = json.load(open("/tmp/repro_a/manifest.json")); b = json.load(open("/tmp/repro_b/manifest.json"))
fa, fb = a["files"], b["files"]
assert fa.keys() == fb.keys()
bad = [k for k in fa if fa[k]["sha256"] != fb[k]["sha256"] or fa[k]["rows"] != fb[k]["rows"]]
rows = sum(v["rows"] or 0 for v in fa.values())
print(f"files compared: {len(fa)} | data rows: {rows} | mismatches: {len(bad)}")
print("REPRODUCIBLE" if not bad and a["command"] == b["command"] else "NOT REPRODUCIBLE: " + str(bad))
json.dump({k: dict(sha256=v["sha256"], rows=v["rows"]) for k, v in fa.items()}, open("/tmp/repro_checksums.json", "w"), indent=1)
PY
