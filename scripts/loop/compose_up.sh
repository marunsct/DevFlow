#!/usr/bin/env bash
# `docker compose up -d SERVICE...` that does not hang on a container left at Created.
#
#   scripts/loop/compose_up.sh app worker
#
# Measured: a deploy's compose call created the new app container and then waited on it for eight minutes with
# both live runs paused; `docker start` on that container returned at once and compose went on, but the worker was
# never replaced and the deploy did not land. So: a service container still at Created after UNSTICK_AFTER seconds
# is started by hand, and once compose returns, a service whose container is not running its newly built image is
# brought up once more on its own. Exits non-zero only when compose itself failed or was stopped at COMPOSE_UP_MOST.
set -u
UNSTICK_AFTER=${UNSTICK_AFTER:-60}
COMPOSE_UP_MOST=${COMPOSE_UP_MOST:-900}
STEP=${COMPOSE_UP_STEP:-5}

_unstick() {
  local s c
  for s in "$@"; do
    case "$s" in -*) continue ;; esac
    for c in $(docker compose ps -a -q "$s" 2>/dev/null); do
      if [ "$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null)" = created ]; then
        echo "compose_up: $s was left at Created; starting it"
        docker start "$c" >/dev/null 2>&1 || true
      fi
    done
  done
}

_up() {
  docker compose up -d "$@" &
  local pid=$! waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep "$STEP"; waited=$((waited + STEP))
    [ "$waited" -ge "$UNSTICK_AFTER" ] && _unstick "$@"
    if [ "$waited" -ge "$COMPOSE_UP_MOST" ]; then
      echo "compose_up: compose still running after ${waited}s; stopped" >&2
      kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; return 1
    fi
  done
  wait "$pid"
}

_stale() {
  # Each service whose container is not running, or not on the image built for it (`<project>-<service>`).
  local s c want have
  for s in "$@"; do
    c=$(docker compose ps -q "$s" 2>/dev/null | head -1)
    want=$(docker image inspect -f '{{.Id}}' "${COMPOSE_PROJECT_NAME:-langchain}-$s" 2>/dev/null)
    have=$([ -n "$c" ] && docker inspect -f '{{.Image}}' "$c" 2>/dev/null)
    if [ -z "$c" ] || { [ -n "$want" ] && [ "$have" != "$want" ]; }; then
      echo "$s"
    fi
  done
}

_up "$@" || exit 1
for s in $(_stale "$@"); do
  echo "compose_up: $s is not on its new image; bringing it up again"
  _up --no-deps "$s" || exit 1
done
exit 0
