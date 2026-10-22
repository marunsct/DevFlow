"""Scaffold stack packs for real: install, unit smoke test, acceptance smoke test.

Runs INSIDE the worker (or a container of a candidate image), piped in on stdin:

    docker compose exec -T worker python - [pack ...] < scripts/loop/verify_packs.py

With no names, every pack. Each is scaffolded into a throwaway workspace under
`/app/data/workspaces/default/pack-check/`, with the run's toolchain marker set
as a run would set it, through exactly the commands a run uses. A pack whose
smoke tests do not pass here leaves every run built on it "left to the agents";
run this after changing a pack, the image's toolchains or a pinned version.
"""
import shutil
import sys
import time
from pathlib import Path

from app.stacks import pack_named
from app.stacks.packs import ALL_PACKS
from app.stacks.scaffold import scaffold
from app.tools.sandbox import STACK_MARKER, _toolchain_keys

base = Path("/app/data/workspaces/default/pack-check")
names = sys.argv[1:] or [pack.name for pack in ALL_PACKS]
failed = []
for name in names:
    pack = pack_named(name)
    root = base / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    keys = _toolchain_keys(pack.language, "javascript")
    (root / STACK_MARKER).write_text("\n".join(sorted(keys)) + "\n")
    started = time.time()
    result = scaffold(root, pack, "demo-app", "Demo App", package="demo_app")
    print(f"=== {name}: ok={result.ok} in {time.time() - started:.0f}s {result.problem}", flush=True)
    if not result.ok:
        failed.append(name)
        for step in result.steps:
            print(f"--- {step['command']} -> exit {step['exit_code']}\n{step['output'][-2500:]}", flush=True)
print(f"{len(names) - len(failed)} of {len(names)} packs scaffolded; failed: {failed or 'none'}")
