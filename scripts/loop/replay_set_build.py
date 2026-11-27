"""Build the diagnosis's replay set from benchmark runs' transcripts (DX.8, minimal; `app.models.replay_set`).

    python scripts/loop/replay_set_build.py <transcripts folder> [--families a,b,c] [--out folder]

Reads only the runs scored against a benchmark family's own brief (`data/bench`), never the owner's own runs, and
writes, for each stage kind (step, reading, opening) and each family named, the most reasoning-heavy request of that
kind whose recorded reply passed its own checks, scrubbed of run ids and host paths. An item holding a run id, a host
path or a line of any benchmark's hidden tests is refused. Reads transcripts; sends nothing to any model.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from app.models import replay_set  # noqa: E402


def _records(path: Path):
    with path.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcripts", type=Path)
    parser.add_argument("--families", default="")
    parser.add_argument("--bench", type=Path, default=ROOT / "data" / "bench")
    parser.add_argument("--benchmarks", type=Path, default=ROOT / "benchmarks")
    parser.add_argument("--out", type=Path, default=replay_set.ITEMS_DIR)
    parser.add_argument("--per-kind", type=int, default=3)
    args = parser.parse_args(argv)
    runs = replay_set.benchmark_runs(args.bench, args.benchmarks)
    wanted = {f for f in args.families.split(",") if f}
    hidden = replay_set.hidden_lines(args.benchmarks)
    best: dict[tuple[str, str], tuple[int, replay_set.Item]] = {}
    for path in sorted(args.transcripts.glob("run-*.jsonl")):
        family = runs.get(path.stem)
        if family is None or (wanted and family not in wanted):
            continue
        for weight, item in replay_set.candidates(_records(path), family):
            why = replay_set.leaks(item, hidden)
            if why:
                print(f"  refused {item.id}: {', '.join(why)}")
                continue
            key = (item.kind, family)
            if key not in best or weight > best[key][0]:
                best[key] = (weight, item)
    # Per kind, the first `--per-kind` families in the order named that gave an item.
    order = [f for f in args.families.split(",") if f] or sorted({family for _kind, family in best})
    chosen = {}
    for kind in ("step", "reading", "opening"):
        for family in [f for f in order if (kind, f) in best][:args.per_kind]:
            chosen[(kind, family)] = best[(kind, family)]
    args.out.mkdir(parents=True, exist_ok=True)
    for (kind, family), (weight, item) in sorted(chosen.items()):
        target = args.out / f"{kind}-{family}.json.gz"
        target.write_bytes(gzip.compress((json.dumps(asdict(item), sort_keys=True) + "\n").encode("utf-8"), mtime=0))
        print(f"  {target.name}: {item.notes.get('stage')}, recorded reasoning {weight:,} characters, "
              f"{len(json.dumps(item.messages)):,} characters of messages")
    print(f"replay set {replay_set.set_hash(replay_set.load(args.out))}: {len(chosen)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
