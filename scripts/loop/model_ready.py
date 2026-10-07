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
    request = urllib.request.Request(
        base + "/models", headers={"Authorization": f"Bearer {key}"} if key else {}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            served = [str(m.get("id")) for m in json.load(reply).get("data", [])]
    except urllib.error.HTTPError as error:
        return False, f"NOTREADY {head} (HTTP {error.code} with the configured key)"
    except Exception as error:  # noqa: BLE001 - any failure is "not ready"
        return False, f"NOTREADY {head} ({type(error).__name__}: {str(error)[:80]})"
    if s.model_name in served:
        return True, f"READY {head} ({len(served)} models listed)"
    return False, f"NOTREADY {head} (served there: {served[:20]})"


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
