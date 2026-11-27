"""The served model's diagnosis: tools forced and offered, reasoning switches, reply salvage (app.models.diagnostics).

Runs INSIDE the worker - `scripts/loop/loop.sh diagnose` - and prints what is
kept for the model the server holds now. A model never diagnosed is diagnosed
first (a few minutes of small requests); `--again` diagnoses it afresh and
keeps the new result; `--deep` also asks whether it does as a stage asks
and keeps the guidance lines that helped (`app.models.deep_diagnosis`), then measures the speed and concurrency profile
and the reasoning dose-response quick tier (`speed_profile`, `dose_response`; `--profile` for those alone). Uses the
owner's model: run it between runs, never
while a stage waits for the server. Changes no server setting.
"""
import os
import sys

from app.models import build_default_chat_model, server_profile
from app.models import diagnostics, reply_salvage

server_profile.record()
model = build_default_chat_model()
name = reply_salvage.served_name(model)
diagnosis = None if "--again" in sys.argv else diagnostics.recorded(name)
if diagnosis is None:
    print(f"diagnosing {name} ...", flush=True)
    diagnosis = diagnostics.diagnose(model, name)
    diagnostics.keep(diagnosis)
print(diagnostics.report(diagnosis))
os.environ.setdefault("REPLY_SALVAGE", "on")
support = None if "--again" in sys.argv else reply_salvage.recorded(name)
support = support or reply_salvage.measure(model, name)
print(f"  reply salvage: {reply_salvage.describe(support)}")

if "--deep" in sys.argv:
    from app.models import deep_diagnosis

    deep = None if "--again" in sys.argv else deep_diagnosis.recorded(name)
    if deep is None:
        print(f"deep diagnosis of {name} ...", flush=True)
        made = deep_diagnosis.diagnose(model, name)  # side by side up to the server's free slots
        deep_diagnosis.keep(made)
        print(deep_diagnosis.report(made))
    else:
        print(f"  deep diagnosis kept {deep.get('measured_at')}: {len(deep.get('kept') or [])} guidance line(s), "
              f"reply ceiling {deep.get('reply_ceiling') or 'none'} (--deep --again to measure afresh)")

if "--deep" in sys.argv or "--profile" in sys.argv:
    # The speed, cache and concurrency profile (DX.6, alone on the server) and the reasoning dose-response's quick
    # tier on replayed stage requests (DX.7). Its full tier starts only from the settings page (owner 2026-11-27).
    from app.models import diagnosis_profile, dose_response, speed_profile

    print(f"speed and concurrency of {name} ...", flush=True)
    speed_profile.measure(model, name)
    print(f"reasoning dose-response of {name} (quick tier) ...", flush=True)
    dose_response.measure(model, name, dose_response.QUICK)
    for row in diagnosis_profile.view(name):
        if row["measured"] is not None or row["override"] is not None:
            print(f"  {row['title']}: measured {row['measured']}, yours {row['override']}, in use {row['applied']}"
                  + (f" - {row['evidence']}" if row["evidence"] else ""))
