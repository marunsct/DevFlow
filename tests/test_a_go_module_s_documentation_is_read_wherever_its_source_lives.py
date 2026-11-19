"""A Go module's documentation is read from the Go documentation site, wherever its source lives.

Measured on one Go run: the architect asked twice how to open `modernc.org/sqlite` through `database/sql`; the module
lives on its own domain, only GitHub-hosted modules had a README this read reached, and it was told twice that
nothing was found.
"""
from __future__ import annotations

from app.tools import docs

PAGE = """<!doctype html><html><body><header>site</header><main>
<h2>Overview</h2><p>Package sqlite is a cgo-free port of SQLite. Import it for its side effect and open a
database with <code>sql.Open("sqlite", "file.db")</code> through database/sql.</p>
<h2>Index</h2><p>func (d *Driver) Open(name string) (driver.Conn, error)</p></main></body></html>"""


def test_a_module_on_its_own_domain_is_read_from_the_go_documentation_site(monkeypatch):
    asked = []

    def fetch(url):
        asked.append(url)
        if url == "https://pkg.go.dev/modernc.org/sqlite":
            return 200, PAGE, "text/html; charset=utf-8"
        return 404, "", ""

    monkeypatch.setattr(docs, "enabled", lambda: True)
    answer = docs.read("modernc.org/sqlite", "opening a database connection with database/sql", "go", fetch=fetch)

    assert "https://pkg.go.dev/modernc.org/sqlite" in asked
    assert 'sql.Open("sqlite"' in str(answer) and "error" not in answer


def test_the_go_documentation_site_is_a_host_a_read_may_reach():
    assert docs._allowed("https://pkg.go.dev/golang.org/x/net")  # noqa: SLF001
