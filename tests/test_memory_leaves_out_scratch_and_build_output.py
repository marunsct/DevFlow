"""The project memory every stage reads leaves out the harness's scratch files and packaging output.

Measured on one run: an acceptance author's memory held four one-line `tmp-inline-` files - code the
harness saved from command lines, which stays in the transcript - and four `*.egg-info` files an install
wrote, each named again in the list of files "already in front of you".
"""
from app.agents import project_memory


def test_scratch_and_packaging_output_are_not_held(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def run():\n    pass\n")
    (tmp_path / "app" / "tmp-inline-0123abcd.py").write_text("print(1)\n")
    (tmp_path / "app" / "app.egg-info").mkdir()
    (tmp_path / "app" / "app.egg-info" / "SOURCES.txt").write_text("app/main.py\n")
    (tmp_path / "app" / "x-1.0.dist-info").mkdir()
    (tmp_path / "app" / "x-1.0.dist-info" / "METADATA").write_text("Name: x\n")

    held = project_memory.current(tmp_path)

    assert "app/main.py" in held
    assert not [p for p in held if "tmp-inline-" in p or ".egg-info" in p or ".dist-info" in p]


def test_a_file_a_stage_named_tmp_is_still_held(tmp_path):
    (tmp_path / "tmp-notes.py").write_text("x = 1\n")
    assert "tmp-notes.py" in project_memory.current(tmp_path)


def test_the_harness_s_bookkeeping_files_are_not_held(tmp_path):
    """Measured on one run: a fixer's memory opened on `.work-order-files.json` - which stage wrote which file -
    before any of the product's code."""
    (tmp_path / ".work-order-files.json").write_text('{"app/main.py": "specialist_backend_0"}\n')
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n")
    held = project_memory.current(tmp_path)
    assert ".work-order-files.json" not in held and "app/main.py" in held
