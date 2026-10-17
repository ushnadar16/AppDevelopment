"""Fold coverage.py JSON output into the six graded backend areas (Section 9.3)."""
import json
import sys

AREAS = {
    "fixtures": ["fixtures.py"],
    "scoring": ["scoring.py", "sports.py"],
    "standings": ["standings.py"],
    "store": ["store.py"],
    "roster": ["roster.py"],
    "rbac": ["rbac.py"],
}

data = json.load(open(sys.argv[1]))
files = {k.replace("\\", "/").rsplit("/", 1)[-1]: v["summary"] for k, v in data["files"].items()}
out = {}
for area, mods in AREAS.items():
    stmts = sum(files[m]["num_statements"] for m in mods)
    covered = sum(files[m]["covered_lines"] for m in mods)
    out[area] = round(100.0 * covered / stmts, 1) if stmts else 0.0
print(json.dumps(out))
if len(sys.argv) > 2:
    json.dump(out, open(sys.argv[2], "w"), indent=2)
