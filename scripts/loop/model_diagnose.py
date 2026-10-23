"""The served model's diagnosis: tools forced and offered, reasoning switches, reply salvage (app.models.diagnostics).

Runs INSIDE the worker - `scripts/loop/loop.sh diagnose` - and prints what is
kept for the model the server holds now. A model never diagnosed is diagnosed
first (a few minutes of small requests); `--again` diagnoses it afresh and
keeps the new result. Uses the owner's model: run it between runs, never
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
