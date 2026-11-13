"""The mutation probe never turns a markup tag's or a type argument's bracket into a comparison.

Measured on a React release: 7 of 12 changes turned `<h1`, `</div>` or a tag's closing `>` into a comparison, the
build broke, every test failed and each change was inconclusive, so the score measured nothing there.
"""
from app.acceptance import mutation

TSX = """export function App() {
  const [items, setItems] = useState<Item[]>([]);
  const shown = items.filter((i) => i.done === wanted);
  if (shown.length > 3 && count < limit) {
    return null;
  }
  return (
    <ul style={{ margin: 0 }}>
      <li>{shown.length}</li>
      <button
        disabled={count<1}
      >
      <div
        style={{ margin: 0
        }}>
      </div>
      </button>
    </ul>
  );
}
"""


def _sites(tmp_path, text, name="App.tsx"):
    path = tmp_path / name
    path.write_text(text)
    return mutation.sites([path], tmp_path)


def test_tags_and_type_arguments_are_left_alone(tmp_path):
    lines = TSX.splitlines()
    found = [(s["line"], s["original"]) for s in _sites(tmp_path, TSX) if s["original"] in ("<", ">")]
    for number, original in found:
        line = lines[number - 1]
        assert "if (" in line or "count<1" in line, (number, original, line)
    assert (4, ">") in found and (4, "<") in found  # the real comparisons are still changed


def test_a_python_comparison_is_unchanged_by_the_rule(tmp_path):
    found = [s["original"] for s in _sites(tmp_path, "def f(a, b):\n    return a<b\n", "f.py")]
    assert "<" in found
