"""An HTTP service in Go, on Gin."""

from __future__ import annotations

from app.stacks.packs import go_http_api as go
from app.stacks.packs._service import service_pack
from app.stacks.packs import _sandbox as sandbox

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
<module>`; keep `go.mod` and `go.sum` tidy with `go mod tidy`.
The module path is `{{package}}` (its `go.mod`), not the project folder's name: a package in a
subfolder `store/` is imported as `{{package}}/store`, and its files say `package store`."""

#: The pack's golden example (`StackPack.golden_example`), in Gin 1.10: path parameters written `:id`, a body read with
#: `ShouldBindJSON` (which answers nothing itself), and the store shared with the standard-library pack's.
GOLDEN_SERVER = r"""package main

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
)

// NewServer builds the service's router. main.go starts it; unit tests call it directly.
func NewServer() http.Handler {
	gin.SetMode(gin.ReleaseMode)
	store := NewStore()
	router := gin.New()
	router.Use(gin.Recovery())
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})
	router.POST("/items", func(c *gin.Context) {
		var body struct {
			Name string `json:"name"`
		}
		if err := c.ShouldBindJSON(&body); err != nil || strings.TrimSpace(body.Name) == "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "name is required"})
			return
		}
		item, err := store.Add(strings.TrimSpace(body.Name))
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "the item could not be stored"})
			return
		}
		c.JSON(http.StatusCreated, item)
	})
	router.GET("/items/:id", func(c *gin.Context) {
		id, err := strconv.Atoi(c.Param("id"))
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "item not found"})
			return
		}
		item, found, err := store.Find(id)
		switch {
		case err != nil:
			c.JSON(http.StatusInternalServerError, gin.H{"error": "the items could not be read"})
		case !found:
			c.JSON(http.StatusNotFound, gin.H{"error": "item not found"})
		default:
			c.JSON(http.StatusOK, item)
		}
	})
	return router
}
"""

PACK = service_pack(
    golden_example={"server.go": GOLDEN_SERVER, "store.go": go.GOLDEN_STORE, "items_test.go": go.GOLDEN_TEST},
    sandbox_image=sandbox.GO,
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
    entrypoint="server.go",
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
