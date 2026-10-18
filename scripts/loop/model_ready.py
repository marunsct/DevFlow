"""Are the models the settings name being served at the addresses the settings name?

Runs INSIDE the worker, with the harness's own resolved settings and keys:

    docker compose exec -T worker python - < scripts/loop/model_ready.py

or `scripts/loop/loop.sh ready`. Prints one line per model - the default one,
and the judgement model when one is configured: READY ..., or NOTREADY ... .
The last line is ALL READY only when every configured model is. Never prints a
key. Run it before every `bench`/`start`: the owner changes the model and the
settings without saying so, and a run on a model that is not served stalls
with nothing in the log.
"""
import json
import urllib.error
import urllib.request

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
        return True, f"READY {head} ({len(served)} models listed){server_facts(reached, naming, key)}"
    return False, f"NOTREADY {head} (served there: {served[:20]})"


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


results = [check("default", _runtime_settings())]
try:
    from app.models.roles import judgement_environment
    from app.server.runtime_settings import effective_environment

    judging = judgement_environment(effective_environment())
except Exception:  # noqa: BLE001 - an image without roles has no second model
    judging = None
if judging is not None:
    results.append(check("judgement", load_settings(judging)))
for ok, line in results:
    print(line)
print("ALL READY" if all(ok for ok, _ in results) else "NOT ALL READY")
# Non-zero when not ready, so `loop.sh ready && loop.sh bench ...` never starts
# a run on a model other than the one the settings name. It used to exit 0 -
# and one run was started on a model the owner had just swapped in.
raise SystemExit(0 if all(ok for ok, _ in results) else 1)
