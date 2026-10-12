"""An HTTP service in Go, on the standard library's `net/http`."""

from __future__ import annotations

from app.stacks.packs._service import service_pack

GO_VERSION = "1.24"

GO_MOD = """module {{package}}

go %s
""" % GO_VERSION

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
module with `go get <module>`; keep `go.mod` and `go.sum` tidy with `go mod tidy`."""

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

PACK = service_pack(
    name="go-http-api",
    title="HTTP service in Go on the standard library",
    language="go",
    frameworks=("net/http", "go", "golang", "standard library", "stdlib"),
    files={
        "go.mod": GO_MOD,
        "main.go": MAIN,
        "server.go": SERVER,
    },
    install=(("go", "build", "./..."),),
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
