"""The owner's direction reaches every model call of a run, not only the calls agents make.

Measured on 2026-11-06: steering notes were added by the agents' instruction middleware alone, and 14 call sites make
model calls outside an agent - drafting (which writes the product's files in fast delivery), rewritten fixes, the
specification's parts, localisation, rulings, the research brief and more - so a direction never reached the code
the product is written in.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.server import steering


def test_a_direct_call_carries_the_run_s_direction(tmp_path, monkeypatch):
    steering.add(tmp_path, "Use a dark colour scheme.", "owner")
    monkeypatch.setattr(steering, "_the_workspace_of", lambda run_id: tmp_path)
    monkeypatch.setattr(steering, "_this_call_s_run_and_stage", lambda: ("run-1", "drafting"))

    sent = steering.with_the_direction([SystemMessage(content="You write files."), HumanMessage(content="app.js")])

    assert "Use a dark colour scheme." in sent[0].content and sent[0].content.startswith("You write files.")
    assert len(sent) == 2 and sent[1].content == "app.js"


def test_a_call_that_already_carries_it_is_left_alone(tmp_path, monkeypatch):
    steering.add(tmp_path, "Use a dark colour scheme.", "owner")
    monkeypatch.setattr(steering, "_the_workspace_of", lambda run_id: tmp_path)
    monkeypatch.setattr(steering, "_this_call_s_run_and_stage", lambda: ("run-1", "specialist_ui_ux_0"))
    carried = steering.as_instructions(tmp_path, "specialist_ui_ux_0", "run-1")
    messages = [SystemMessage(content="You build the page." + carried), HumanMessage(content="go")]

    assert steering.with_the_direction(messages) == messages


def test_no_note_or_no_run_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(steering, "_the_workspace_of", lambda run_id: tmp_path)
    monkeypatch.setattr(steering, "_this_call_s_run_and_stage", lambda: ("run-1", "drafting"))
    messages = [HumanMessage(content="app.js")]
    assert steering.with_the_direction(messages) == messages
    monkeypatch.setattr(steering, "_this_call_s_run_and_stage", lambda: (None, None))
    steering.add(tmp_path, "x", "owner")
    assert steering.with_the_direction(messages) == messages


def test_a_call_with_no_system_message_gets_one_first(tmp_path, monkeypatch):
    steering.add(tmp_path, "Keep titles under 80 characters.", "owner")
    monkeypatch.setattr(steering, "_the_workspace_of", lambda run_id: tmp_path)
    monkeypatch.setattr(steering, "_this_call_s_run_and_stage", lambda: ("run-1", "research_brief"))

    sent = steering.with_the_direction([HumanMessage(content="brief")])

    assert isinstance(sent[0], SystemMessage) and "80 characters" in sent[0].content and sent[1].content == "brief"


def test_the_shared_chat_model_applies_it():
    import inspect

    from app.models import CompatibleChatOpenAI

    assert "with_the_direction(" in inspect.getsource(CompatibleChatOpenAI._generate)


def test_notes_sent_at_once_are_all_kept(tmp_path):
    """The API adds a note while worker threads mark notes read; both rewrote the file unlocked, so one could
    silently drop the other's note - the more so with a live chat sending many."""
    import threading

    def send(n):
        steering.add(tmp_path, f"note {n}", "owner")

    def read():
        for _ in range(20):
            steering.as_instructions(tmp_path, "drafting", "run-1")

    threads = [threading.Thread(target=send, args=(n,)) for n in range(30)] + [threading.Thread(target=read) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    kept = steering.notes(tmp_path)
    assert sorted(n["text"] for n in kept) == sorted(f"note {n}" for n in range(30))
    assert len({n["id"] for n in kept}) == 30
