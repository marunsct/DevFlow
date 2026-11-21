"""An HTTP service in Go, on the standard library's `net/http`."""

from __future__ import annotations

from app.stacks.packs._service import service_pack
from app.stacks.packs import _sandbox as sandbox

GO_VERSION = "1.26"

GO_MOD = """module {{package}}

go %s
""" % GO_VERSION

#: The `go` line the module keeps, at every round (`StackPack.required_signatures`): the standard library's routing by
#: method and path (`"GET /notes/{id}"`) needs Go 1.22. Measured on one run: a backend work order rewrote `go.mod` to
#: `go 1.21`, every route then answered 404, and the product did not start for the acceptance suite.
GO_LINE = {"go.mod": ((r"^go\s+1\.(?:2[2-9]|[3-9]\d)(?:\.\d+)?\s*$", f"go {GO_VERSION}"),)}

MAIN = """package main

import (
	"log"
	"net/http"
	"os"
)

func main() {
	host := getenv("HOST", "127.0.0.1")
	port := getenv("PORT", "8080")
	log.Printf("Listening on http://%s:%s", host, port)
	log.Fatal(http.ListenAndServe(host+":"+port, NewServer()))
}

func getenv(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
"""

SERVER = """package main

import (
	"encoding/json"
	"net/http"
)

// NewServer builds the service's handler. main.go starts it; unit tests call it directly.
func NewServer() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	return mux
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
"""

SMOKE_UNIT = """package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestTheServiceReportsItsHealth(t *testing.T) {
	recorder := httptest.NewRecorder()
	NewServer().ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/health", nil))
	if recorder.Code != http.StatusOK || recorder.Body.String() != "{\\"status\\":\\"ok\\"}\\n" {
		t.Fatalf("health answered %d %q", recorder.Code, recorder.Body.String())
	}
}
"""

GUIDE = """The service is Go on the standard library: `NewServer()` in `server.go` builds its
`http.Handler` (route with Go 1.22 patterns, `mux.HandleFunc("POST /items", ...)`), and
`main.go` starts it. Unit tests sit beside the code they test, in `<name>_test.go`
files of the same package, using `testing` and `net/http/httptest` to call the
handler directly. Run them with `gotestsum -- ./...` (or `go test ./...`). Add a
module with `go get <module>`; keep `go.mod` and `go.sum` tidy with `go mod tidy`.
The module path is `{{package}}` (its `go.mod`), not the project folder's name: a package in a
subfolder `store/` is imported as `{{package}}/store`, and its files say `package store`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8080:8080 -v {{project}}-data:/data {{project}}`.
FROM golang:%(go)s AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/server .

FROM gcr.io/distroless/static-debian12:nonroot
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/data
COPY --from=build /out/server /server
USER nonroot:nonroot
EXPOSE 8080
ENTRYPOINT ["/server"]
""" % {"go": GO_VERSION}

#: The Go packs' golden example's store (`StackPack.golden_example`): one JSON file under DATA_DIR, one lock held
#: across each read-change-write, the new id taken inside it.
GOLDEN_STORE = r"""package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync"
)

// Item is one stored record.
type Item struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

// Store keeps the items in one JSON file under DATA_DIR; its lock covers each read-change-write.
type Store struct {
	mu   sync.Mutex
	path string
}

// NewStore reads DATA_DIR when the service is built, so a test sets it first.
func NewStore() *Store {
	dir := os.Getenv("DATA_DIR")
	if dir == "" {
		dir = "data"
	}
	return &Store{path: filepath.Join(dir, "items.json")}
}

// Add stores a new item, its id taken under the same lock as the write.
func (s *Store) Add(name string) (Item, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items, err := s.load()
	if err != nil {
		return Item{}, err
	}
	item := Item{ID: 1, Name: name}
	for _, existing := range items {
		if existing.ID >= item.ID {
			item.ID = existing.ID + 1
		}
	}
	return item, s.save(append(items, item))
}

// Find returns the item with this id, and whether there is one.
func (s *Store) Find(id int) (Item, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items, err := s.load()
	if err != nil {
		return Item{}, false, err
	}
	for _, item := range items {
		if item.ID == id {
			return item, true, nil
		}
	}
	return Item{}, false, nil
}

func (s *Store) load() ([]Item, error) {
	data, err := os.ReadFile(s.path)
	if errors.Is(err, os.ErrNotExist) {
		return []Item{}, nil
	}
	if err != nil {
		return nil, err
	}
	var items []Item
	if err := json.Unmarshal(data, &items); err != nil {
		return nil, err
	}
	return items, nil
}

func (s *Store) save(items []Item) error {
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return err
	}
	data, err := json.Marshal(items)
	if err != nil {
		return err
	}
	return os.WriteFile(s.path, data, 0o644)
}
"""

GOLDEN_SERVER = r"""package main

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
)

// NewServer builds the service's handler. main.go starts it; unit tests call it directly.
func NewServer() http.Handler {
	store := NewStore()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("POST /items", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Name string `json:"name"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Name) == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "name is required"})
			return
		}
		item, err := store.Add(strings.TrimSpace(body.Name))
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "the item could not be stored"})
			return
		}
		writeJSON(w, http.StatusCreated, item)
	})
	mux.HandleFunc("GET /items/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.Atoi(r.PathValue("id"))
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "item not found"})
			return
		}
		item, found, err := store.Find(id)
		switch {
		case err != nil:
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "the items could not be read"})
		case !found:
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "item not found"})
		default:
			writeJSON(w, http.StatusOK, item)
		}
	})
	return mux
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
"""

GOLDEN_TEST = r"""package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
)

func send(server http.Handler, method, path, body string) *httptest.ResponseRecorder {
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	server.ServeHTTP(recorder, request)
	return recorder
}

func TestAnItemIsStoredAndReadBack(t *testing.T) {
	t.Setenv("DATA_DIR", t.TempDir())

	created := send(NewServer(), http.MethodPost, "/items", `{"name":"first"}`)
	if created.Code != http.StatusCreated {
		t.Fatalf("create answered %d %s", created.Code, created.Body.String())
	}
	var item Item
	if err := json.Unmarshal(created.Body.Bytes(), &item); err != nil {
		t.Fatal(err)
	}
	// A service built afresh reads what the first one stored.
	found := send(NewServer(), http.MethodGet, "/items/"+strconv.Itoa(item.ID), "")
	if found.Code != http.StatusOK || !strings.Contains(found.Body.String(), `"name":"first"`) {
		t.Fatalf("read answered %d %s", found.Code, found.Body.String())
	}
}

func TestAMissingNameIsRefusedAndAnUnknownIDIsNotFound(t *testing.T) {
	t.Setenv("DATA_DIR", t.TempDir())
	server := NewServer()

	if refused := send(server, http.MethodPost, "/items", `{}`); refused.Code != http.StatusBadRequest {
		t.Fatalf("a missing name answered %d", refused.Code)
	}
	if missing := send(server, http.MethodGet, "/items/99", ""); missing.Code != http.StatusNotFound {
		t.Fatalf("an unknown id answered %d", missing.Code)
	}
}
"""

#: Errors a Go project is known to raise, by a phrase of the compiler's message, and their cause
#: (`app.stacks.known_errors`); every Go pack carries them.
GO_KNOWN_ERRORS = {
    # Measured on one Go run: `go.mod` said `module notes-api`, the files imported `notes_api/store`, and `store.go`
    # sat beside `main.go` as `package main` - three test rounds and two rewrites left the import as it was.
    "is not in std": (
        "Go read that import as a standard-library package: its first part is not this module's path. A package of "
        "this project is imported as the `module` line of `go.mod` plus its folder - `module notes-api` and a folder "
        "`store/` holding `package store` is `import \"notes-api/store\"`. Files in the project's top folder are all "
        "`package main` and use each other's names with no import at all: either move the code into that folder "
        "with its own package name, or drop the import."
    ),
    # Measured on one Go run: `server_test.go` said `package server` and `store.go` said `package store` beside
    # `main.go`'s `package main`; the product did not start, and the first fix left the package lines as they were.
    "found packages": (
        "A Go folder holds one package: every `.go` file in it declares the same `package` line (a test file may add "
        "`_test` to it). A file declaring another name belongs in its own subfolder, imported as the `module` path plus "
        "that folder (`notes-api/store`); in the top folder, make `main.go`, the server, the store and their tests all "
        "`package main`."
    ),
}

PACK = service_pack(
    golden_example={"server.go": GOLDEN_SERVER, "store.go": GOLDEN_STORE, "items_test.go": GOLDEN_TEST},
    known_errors=GO_KNOWN_ERRORS,
    required_signatures=GO_LINE,
    sandbox_image=sandbox.GO,
    name="go-http-api",
    entrypoint="server.go",
    title="HTTP service in Go on the standard library",
    language="go",
    frameworks=("net/http", "go", "golang", "standard library", "stdlib"),
    files={
        "go.mod": GO_MOD,
        "main.go": MAIN,
        "server.go": SERVER,
    },
    # Tidied first, where a command has a network (LF.1134): a drafted `go.mod` that does not match the imports
    # fails every build with "go mod tidy", and no fixer's command can fetch a module.
    install=(("go", "mod", "tidy"), ("go", "build", "./...")),
    unit_test=("gotestsum", "--junitfile", "test-results/unit.xml", "--format", "standard-quiet", "--", "./..."),
    unit_report="test-results/unit.xml",
    unit_dir=".",
    unit_pattern="*_test.go",
    start="go build -o bin/server . && exec ./bin/server",
    server_timeout_ms=180_000,
    smoke_unit=("scaffold_smoke_test.go", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "Go",
        "framework": "net/http (standard library)",
        "frontend_framework": "",
        "testing_framework": "go test (reported by gotestsum) for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(
        "      - uses: actions/setup-go@v5\n"
        "        with:\n"
        f'          go-version: "{GO_VERSION}"\n'
        "      - run: go install gotest.tools/gotestsum@v1.12.3",
    ),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\nbin/\nacceptance/\ndata/\n"},
    gitignore="bin/\n",
)
