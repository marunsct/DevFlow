"""Can the build model call tools well enough for a run? (app.models.fitness)

Runs INSIDE the worker:

    docker compose exec -T worker python - < scripts/loop/model_fitness.py

or `scripts/loop/loop.sh fitness`. Five short requests to the default (build)
model; prints FIT / USABLE / UNFIT with the misses and advice. Run it after
`ready` and before a run - never while a run is live, since it takes the
model server's time from the run.
"""
from app.models import build_default_chat_model
from app.models.fitness import probe

result = probe(build_default_chat_model())
print(f"{result.verdict.upper()} build model: {result.passed}/{result.total} probes - {result.advice()}")
for miss in result.misses:
    print(f"  miss {miss}")
