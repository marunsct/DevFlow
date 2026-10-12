"""An HTTP service in Go, on Gin."""

from __future__ import annotations

from app.stacks.packs import go_http_api as go
from app.stacks.packs._service import service_pack

SERVER = """package main

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// NewServer builds the service's router. main.go starts it; unit tests call it directly.
func NewServer() http.Handler {
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.Use(gin.Recovery())
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})
	return router
}
"""

SMOKE_UNIT = go.SMOKE_UNIT.replace('"{\\"status\\":\\"ok\\"}\\n"', '"{\\"status\\":\\"ok\\"}"')
assert SMOKE_UNIT != go.SMOKE_UNIT, "the Go smoke test no longer checks the body the way this replaces"

GUIDE = """The service is Go on Gin: `NewServer()` in `server.go` builds its router (add routes
with `router.POST("/items", create)`; group them with `router.Group`), and `main.go`
starts it. Unit tests sit beside the code they test, in `<name>_test.go` files of the
same package, using `testing` and `net/http/httptest` to call the router directly.
Run them with `gotestsum -- ./...` (or `go test ./...`). Add a module with `go get
<module>`; keep `go.mod` and `go.sum` tidy with `go mod tidy`."""

PACK = service_pack(
    name="go-gin-api",
    title="HTTP service in Go on Gin",
    language="go",
    frameworks=("gin", "gin-gonic"),
    files={
        # Gin 1.10: later releases add HTTP/3 and a database driver to every
        # build, more than a service's sandbox has memory to compile.
        "go.mod": go.GO_MOD + "\nrequire github.com/gin-gonic/gin v1.10.0\n",
        "main.go": go.MAIN,
        "server.go": SERVER,
    },
    install=(("go", "mod", "tidy"), ("go", "build", "./...")),
    unit_test=go.PACK.unit_test,
    unit_report="test-results/unit.xml",
    unit_dir=".",
    unit_pattern="*_test.go",
    start="go build -o bin/server . && exec ./bin/server",
    server_timeout_ms=180_000,
    smoke_unit=("scaffold_smoke_test.go", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "Go",
        "framework": "Gin",
        "frontend_framework": "",
        "testing_framework": "go test (reported by gotestsum) for unit tests, Playwright (request fixture) for acceptance tests",
    },
    # Go's own setup step; `service_pack` adds Node's for the acceptance suite.
    ci_setup=go.PACK.ci_setup[:1],
    release_files=dict(go.PACK.release_files),
    gitignore="bin/\n",
)
