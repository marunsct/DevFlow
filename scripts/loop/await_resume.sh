#!/bin/sh
# After a deploy while a run was live: wait (up to 10 minutes) for orphan
# recovery to resume it, i.e. for the worker to make model calls again.
#
#     scripts/loop/await_resume.sh        or        scripts/loop/loop.sh resumed
#
# Prints "model calls resumed (N)" with the worker's recovery lines, or
# "no resume after 10 minutes" - then look at `loop.sh status` and the worker
# log. Lines that mention an API key are never printed.
cd "$(dirname "$0")/../.." || exit 1
for i in $(seq 1 20); do
  hit=$(docker compose logs worker --since 10m 2>/dev/null | grep -v -i "api[_-]key" | grep -i -E "orphan|resum|recover" | tail -3)
  calls=$(docker compose logs worker --since 10m 2>/dev/null | grep -c "chat/completions")
  if [ "$calls" -gt 0 ]; then echo "model calls resumed ($calls); $hit"; exit 0; fi
  sleep 30
done
echo "no resume after 10 minutes"; docker compose logs worker --since 12m 2>/dev/null | grep -v -i "api[_-]key" | grep -i -E "orphan|resum|recover" | tail -5
