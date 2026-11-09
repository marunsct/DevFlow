"""loop.sh reaches the worker and the database by their compose service, not a fixed container name.

A recreate interrupted by a restart leaves a container named `<id>_langchain-worker-1`; a fixed name then
finds nothing and every score fails with "No such container".
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOOP = (ROOT / "scripts" / "loop" / "loop.sh").read_text()


def test_no_command_names_a_fixed_container():
    commands = [line for line in LOOP.splitlines() if not line.lstrip().startswith("#")]
    fixed = [line for line in commands if re.search(r"langchain-(worker|db|app)-1", line)
             and "||" not in line.split("langchain-")[0][-30:] and ":-langchain-" not in line]
    assert fixed == []


def test_the_containers_are_looked_up_through_compose():
    assert re.search(r'WORKER_C=.*docker compose ps -q worker', LOOP)
    assert re.search(r'DB_C=.*docker compose ps -q db', LOOP)
