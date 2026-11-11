"""Are the models the settings name being served at the addresses the settings name?

Runs INSIDE the worker, with the harness's own resolved settings and keys:

    docker compose exec -T worker python - < scripts/loop/model_ready.py

or `scripts/loop/loop.sh ready`. Prints one line per model - the default one,
and the judgement model when one is configured: READY ..., or NOTREADY ... .
With `pin_url=...` and/or `pin_model=...` (what `start`/`bench` pass for PIN_URL
and PIN_MODEL_NAME), the model checked is that one, with its endpoint's own key.
The last line is ALL READY only when every configured model is. Never prints a
key. Run it before every `bench`/`start`: the owner changes the model and the
settings without saying so, and a run on a model that is not served stalls
with nothing in the log.
"""
import json
import sys
import urllib.error
import urllib.request

#: `loop.sh ready deep`: also send a request of about 13,000 tokens. Measured after the owner reloaded a model: the
#: small request below answered while every real call (tens of thousands of tokens) returned HTTP 500/502, so the
#: check said ALL READY and two runs failed at their first stage. Not the default: it queues behind a live run.
DEEP = "deep" in sys.argv[1:]
DEEP_WORDS = 12000

from app.config import load_settings
from app.models import _runtime_settings


def check(label, s):
    base = (s.openai_base_url or "").rstrip("/")
    key = s.openai_api_key or ""
    head = f"{label} provider={s.llm_provider} model={s.model_name} base={base}"
    if (s.llm_provider or "") in {"anthropic", "gemini"}:
        return True, f"READY {head} (hosted provider; not probed)"
    if not base:
        return False, f"NOTREADY {head} (no base url configured)"
    from app.models.endpoints import reached_from_here

    reached, naming = reached_from_here(base)
    request = urllib.request.Request(
        reached + "/models",
        headers={**({"Authorization": f"Bearer {key}"} if key else {}), **naming},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            served = [str(m.get("id")) for m in json.load(reply).get("data", [])]
    except urllib.error.HTTPError as error:
        return False, f"NOTREADY {head} (HTTP {error.code} with the configured key)"
    except Exception as error:  # noqa: BLE001 - any failure is "not ready"
        return False, f"NOTREADY {head} ({type(error).__name__}: {str(error)[:80]})"
    if s.model_name in served:
        answered = answers(reached, naming, key, s.model_name)
        if not answered and DEEP:
            answered = answers(reached, naming, key, s.model_name, words=DEEP_WORDS)
        if answered:
            busy = live_runs_on(base) if is_a_timeout(answered) else []
            if busy:
                # Still not ready, and `start` still refuses: a second run would wait its turn behind these and the
                # timing of both would mean nothing. Said apart, because the cure is another server or a later
                # start, not a look at the model.
                return False, (f"NOTREADY {head} (BUSY: it lists the model, and a small request timed out while "
                               f"{', '.join(busy[:4])} of ours use this server)")
            return False, f"NOTREADY {head} (listed, but it does not answer a request: {answered})"
        return True, f"READY {head} ({len(served)} models listed){server_facts(reached, naming, key)}"
    return False, f"NOTREADY {head} (served there: {served[:20]})"


def is_a_timeout(said):
    """Whether what `answers` said is a request that ran out of time, rather than a refusal."""
    return "timeout" in str(said).lower() or "timed out" in str(said).lower()


def live_runs_on(base):
    """The live runs of ours whose model is at `base`; [] when none, or when the run store cannot say. Never raises."""
    try:
        from app.server.run_store import RunStore

        store = RunStore.shared()
        live = [r.run_id for r in store.list_all(limit=100) if str(r.status) in ("running", "queued", "pending")]
        states = store.model_states(live)
        wanted = str(base or "").rstrip("/").lower()
        return [run for run in live
                if str(states.get(run, (False, {}))[1].get("OPENAI_BASE_URL") or "").rstrip("/").lower() == wanted]
    except Exception:  # noqa: BLE001 - then it reads as a server that does not answer, as before
        return []


def answers(reached, naming, key, model_name, words=0):
    """"" when the model answers one small request; else what the server said instead.

    Listed is not served: a server that lists every model it has on disk
    answered each request "No model loaded" - the check said ALL READY, a run
    started, and it failed at its first stage while the new model's automatic
    diagnosis kept the refusals as the model's own.
    """
    text = ("Reply with: ready" if not words
            else ("The quick brown fox jumps over the lazy dog. " * (words // 9 + 1))[: words * 6] + "\nReply with: ready")
    body = json.dumps({"model": model_name, "messages": [{"role": "user", "content": text}],
                       "max_tokens": 16, "stream": False}).encode()
    request = urllib.request.Request(
        reached + "/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {}), **naming},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as reply:
            return "" if json.load(reply).get("choices") else "no choices in its reply"
    except urllib.error.HTTPError as error:
        try:
            said = json.load(error).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            said = ""
        return f"HTTP {error.code} {str(said)[:80]}".strip()
    except Exception as error:  # noqa: BLE001
        return f"{type(error).__name__}: {str(error)[:80]}"


def server_facts(reached, naming, key):
    """What a llama.cpp-style server says of itself at /props: slots, context, quantisation. "" if nothing.

    One slot serves one request at a time: two runs on it each waited for the
    other (a call went from about 40 s to about 5 min), and parallel mode's
    fan-out only queues. The context it was started with is the real ceiling,
    whatever the settings say (one server refused at ~54k with 131k set).
    The harness applies both itself now (`app.models.server_profile`).
    """
    try:
        from app.models.server_profile import read
    except ImportError:  # an image from before the profile module
        return ""
    profile = read(reached, key)
    if profile is None:
        return ""
    said = []
    if profile.slots:
        said.append(f"{profile.slots} slot(s)" + ("; parallel mode and a second run will wait their turn" if profile.slots == 1 else ""))
    if profile.slot_context:
        said.append(f"context {profile.slot_context} tokens as started")
    if profile.quantisation:
        said.append(profile.quantisation)
    if profile.advisory():
        said.append("ADVISORY " + profile.advisory())
    return f" [server: {', '.join(said)}]" if said else ""


def the_pin_asked_for(argv):
    """The model snapshot a run started with `pin_url=...` / `pin_model=...` will use, as `start` builds it; None for no pin."""
    said = dict(arg.split("=", 1) for arg in argv if arg.startswith(("pin_url=", "pin_model=")))
    # A bare address is the server to check, as `loop.sh ready http://host:8888/v1` is written: read alone it was
    # ignored, and every check of the second port checked the default one instead.
    bare = [arg for arg in argv if arg.startswith(("http://", "https://"))]
    if bare and not said.get("pin_url"):
        said["pin_url"] = bare[0]
    if not any(said.values()):
        return None
    from app.models.model_pin import snapshot_for
    from app.server.runtime_settings import global_model_snapshot

    return snapshot_for(global_model_snapshot(), said.get("pin_url") or None, said.get("pin_model") or None)


# The server the run will use, not the one the settings name: a busy server held back a run pinned to another, which
# sat idle for 15 minutes. Laid over the settings the way a pinned run's is, so each endpoint gets its own key or none.
PINNED = the_pin_asked_for(sys.argv[1:])
if PINNED is None:
    results = [check("default", _runtime_settings())]
else:
    from app.server.runtime_settings import effective_environment as _environment

    results = [check("pinned", load_settings(dict(_environment(model=PINNED))))]
try:
    from app.models.roles import judgement_environment
    from app.server.runtime_settings import effective_environment

    judging = judgement_environment(effective_environment() if PINNED is None else effective_environment(model=PINNED))
except Exception:  # noqa: BLE001 - an image without roles has no second model
    judging = None
if judging is not None:
    results.append(check("judgement", load_settings(judging)))
# Commands, as well as the model (Initiative AH.4): a run on a worker that
# cannot run commands writes a product nothing can install, build or test.
try:
    from app.tools.sandbox import execution_readiness

    can_run, why = execution_readiness()
    results.append((can_run, f"{'READY' if can_run else 'NOTREADY'} commands ({why})"))
except ImportError:  # an image from before the probe
    pass
for ok, line in results:
    print(line)
# What the harness knows of the build model's family, and what it measured
# (Initiative BH). Information only: it never decides readiness.
try:
    from app.models import server_profile
    from app.models.model_guidance import served_as
    from app.models.registry import describe

    # Named as the worker names the model (the server's file), or its measurements read "unmeasured".
    if PINNED is None:
        server_profile.record()
    print("MODEL " + describe(served_as(str((PINNED or {}).get("OPENAI_MODEL") or _runtime_settings().model_name or ""))))
except ImportError:  # an image from before the registry
    pass
print("ALL READY" if all(ok for ok, _ in results) else "NOT ALL READY")
# Non-zero when not ready, so `loop.sh ready && loop.sh bench ...` never starts
# a run on a model other than the one the settings name. It used to exit 0 -
# and one run was started on a model the owner had just swapped in.
raise SystemExit(0 if all(ok for ok, _ in results) else 1)
