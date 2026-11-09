"""Set, or clear, the serving model's reply ceiling from what its runs showed (`loop.sh ceiling <tokens>|none [why]`).

Runs INSIDE the worker. The ceiling is kept in the model's deep-diagnosis record (`reply_ceiling`,
with `reply_ceiling_from` saying why) and applied when a run segment starts, so a run already
going takes it at its next restart. Reply salvage answers a reply cut at the ceiling from its own
reasoning. Never changes the owner's model or server.

    docker compose exec -T worker python - 24000 "why" < scripts/loop/set_ceiling.py
"""
from __future__ import annotations

import json
import sys


def set_ceiling(name: str, tokens: int | None, why: str = "") -> dict:
    from app.models.registry import _slug, fitness_dir, merge_into_fitness

    path = fitness_dir() / f"{_slug(name)}.json"
    record = (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}).get("deep_diagnosis") or {}
    if not record:
        raise SystemExit(f"{name} has no deep diagnosis to keep a ceiling in; diagnose it first")
    if tokens:
        record["reply_ceiling"], record["reply_ceiling_from"] = int(tokens), why or "set by hand"
    else:
        record["reply_ceiling"] = None
        record.pop("reply_ceiling_from", None)
    merge_into_fitness(name, {"deep_diagnosis": record})
    return record


def main(argv: list[str]) -> int:
    from app.models import server_profile
    from app.models.model_guidance import served_now

    server_profile.record()
    name = served_now()
    wanted = argv[1] if len(argv) > 1 else ""
    if not name or wanted == "":
        print("usage: set_ceiling.py <tokens>|none [why]")
        return 2
    kept = set_ceiling(name, None if wanted == "none" else int(wanted), " ".join(argv[2:]))
    print(f"{name}: reply ceiling {kept.get('reply_ceiling') or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
