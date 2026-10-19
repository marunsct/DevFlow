"""Can the build model call tools well enough for a run? (app.models.fitness)

Runs INSIDE the worker:

    docker compose exec -T worker python - < scripts/loop/model_fitness.py

or `scripts/loop/loop.sh fitness`. Five short requests to the default (build)
model; prints FIT / USABLE / UNFIT with the misses and advice. Run it after
`ready` and before a run - never while a run is live, since it takes the
model server's time from the run.

With `--edits` (`loop.sh fitness --edits`) it also measures how often the
model's whole-file writes and find-and-replace edits come back well formed and
keeps the rates under `DATA_DIR/model-fitness/` (Initiative BH).
"""
import sys

from app.models import build_default_chat_model
from app.models.fitness import probe

from app.models import _runtime_settings

result = probe(build_default_chat_model())
name = str(_runtime_settings().model_name or "")
print(f"{result.verdict.upper()} build model: {result.passed}/{result.total} probes - {result.advice(name)}")
for miss in result.misses:
    print(f"  miss {miss}")

if "--edits" in sys.argv:
    from app.models.fitness import edit_probe
    from app.models.registry import describe, record_edit_rates

    name = name or "unknown"
    rates = edit_probe(build_default_chat_model())
    print(f"edits: {rates} -> {record_edit_rates(name, rates)}")
    print(describe(name))
