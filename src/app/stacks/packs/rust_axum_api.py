"""An HTTP service in Rust, on axum and tokio."""

from __future__ import annotations

from app.stacks.packs._service import service_pack
from app.stacks.packs import _sandbox as sandbox
from app.stacks.packs.rust_programs import CARGO_CONFIG

CARGO_TOML = """[package]
name = "{{package}}"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = "0.8"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["macros", "rt-multi-thread", "net"] }

[dev-dependencies]
http-body-util = "0.1"
tower = { version = "0.5", features = ["util"] }
"""

LIB = """use axum::{routing::get, Json, Router};
use serde_json::{json, Value};

/// Builds the service. `main.rs` starts it; unit tests call it directly.
pub fn app() -> Router {
    Router::new().route("/health", get(health))
}

async fn health() -> Json<Value> {
    Json(json!({ "status": "ok" }))
}
"""

MAIN = """#[tokio::main]
async fn main() {
    let host = std::env::var("HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let port = std::env::var("PORT").unwrap_or_else(|_| "3000".into());
    let listener = tokio::net::TcpListener::bind(format!("{host}:{port}"))
        .await
        .expect("the port to be free");
    println!("Listening on http://{host}:{port}");
    axum::serve(listener, {{package}}::app()).await.expect("the service to run");
}
"""

NEXTEST = """# Kept by the harness: the unit tests report through this profile.
[profile.ci.junit]
path = "junit.xml"
"""

SMOKE_UNIT = """use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use tower::ServiceExt;

#[tokio::test]
async fn the_service_reports_its_health() {
    let response = {{package}}::app()
        .oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = response.into_body().collect().await.unwrap().to_bytes();
    assert_eq!(&body[..], br#"{"status":"ok"}"#);
}
"""

#: Measured on one Rust run: its unit tests imported `axum::test`, which does not exist, through two fix rounds, and
#: `app()` returned a `Router<AppState>` that `axum::serve` would not serve; the guide named `oneshot` and neither.
GUIDE = """The service is Rust on axum: `app()` in `src/lib.rs` builds its `Router` (add routes
with `.route("/items", post(create))`), and `src/main.rs` starts it. Unit tests go in
`tests/`, one file per area (`tests/<area>.rs`), calling `{{package}}::app()` with
`tower::ServiceExt::oneshot` - or in a `#[cfg(test)]` module beside the code. There is no
`axum::test`: a test imports `axum::body::Body`, `axum::http::{Request, StatusCode}`,
`http_body_util::BodyExt` and `tower::ServiceExt`, as `tests/scaffold_smoke.rs` does. `app()`
returns a plain `Router`: shared state is applied inside it with `.with_state(state)`, since
`axum::serve` cannot serve a `Router<AppState>`. Its signature is `pub fn app() -> Router`: declared
`-> Router<AppState>`, it still waits for its state after `.with_state`. Run them with `cargo nextest run` (or `cargo
test`). Add a crate with `cargo add <name>`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 3000:3000 -v {{project}}-data:/data {{project}}`.
FROM rust:1 AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo fetch && rm -r src
COPY . .
RUN cargo build --release

FROM debian:trixie-slim
ENV HOST=0.0.0.0 PORT=3000 DATA_DIR=/data
COPY --from=build /src/target/release/{{package}} /usr/local/bin/service
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/service"]
"""

#: Errors an axum service is known to raise, by a phrase of the compiler's message, and their cause
#: (`app.stacks.known_errors`). Measured on two Rust runs: a handler taking `Json` before `State` failed as "`Handler<_, _>`
#: is not satisfied" for three fix rounds, and `axum::serve` given a `Router<AppState>` failed every round of a run.
#: Measured on a Rust run: `app()` ended in `.with_state(state)` yet was declared `-> Router<AppState>`, so the router
#: still waited for its state, and a fixer told to apply the state found it already applied and left the error open.
THE_SIGNATURE_DECIDES = (
    " The return type decides it: `.with_state(state)` gives the router the type the function names, so "
    "`fn app() -> Router<AppState>` still waits for its state after `.with_state` - change the signature in "
    "`src/lib.rs` to `pub fn app() -> Router`; the error shows where the router is used, not where it is typed."
)
AXUM_KNOWN_ERRORS = {
    # Measured on a Rust run, once its crates resolved: the store used sqlx's `query!` macros, which check each query
    # against a live database when the crate compiles; the build has none, and the product could not start.
    "to use query macros online": (
        "sqlx's `query!`, `query_as!` and `query_scalar!` macros check each query against a live database while the "
        "crate compiles, and this build has none. Write each query with sqlx's functions instead - "
        "`sqlx::query(\"... WHERE id = ?\").bind(id)`, `sqlx::query_as::<_, Note>(...)` with `#[derive(sqlx::FromRow)]` "
        "on the struct - in every file that uses a macro, in one rewrite."
    ),
    "is not supported by the following packages": (
        "a crate's newest release needs a newer Rust than this project's toolchain. Do not pin crates by hand: "
        "delete `Cargo.lock` (with `delete_artifact`) so cargo chooses again - `.cargo/config.toml` tells it to "
        "choose the releases this toolchain builds."
    ),
    "Handler<_, _>` is not satisfied": (
        "an axum handler's arguments are extractors, and the one that reads the request body (`Json<T>`, `Form<T>`, "
        "`String`, `Bytes`) must be its last argument, after `State`, `Path` and `Query`: a body extractor earlier in "
        "the list stops the function being a `Handler`. Put it last in every handler of the file in one rewrite."
    ),
    **{phrase: (
        "`app()` must return a plain `Router` whose routes no longer wait for their state: build the state inside "
        "`app()` (from `DATA_DIR`) and end it with `.with_state(state)`; `main.rs` and the tests then use `app()` as "
        "it is, sending a test's requests to it with `oneshot`." + THE_SIGNATURE_DECIDES
    ) for phrase in ("expected `Router`, found `Router<", "exists for struct `Router<")},
    **{phrase: (
        "`oneshot` takes the router by value, so a test that sends a second request through the same router has "
        "already given it away: build it again with `app()` for each request (or send the first through "
        "`.clone()`)."
    ) for phrase in ("use of moved value: `app`", "use of moved value: `router`")},
    "Missing request extension": (
        "a handler takes `Extension<AppState>` while `app()` applies the state with `.with_state(state)`: those are two "
        "mechanisms. Take `State(state): State<AppState>` in every handler (or add `.layer(Extension(state))`, not both)."
    ),
    # Measured on a Rust run: a store set SQLite's journal mode through a `rusqlite::JournalMode` that does not exist;
    # the fixer and two stuck lookups left it open, and a test then named a struct its module only imports.
    "could not find `JournalMode` in `rusqlite`": (
        "rusqlite has no `JournalMode` type: set a pragma with `conn.pragma_update(None, \"journal_mode\", \"WAL\")?` "
        "(or `conn.execute_batch(\"PRAGMA journal_mode=WAL;\")?`), or leave the default journal mode."
    ),
    "as mutable, as it is behind a `&` reference": (
        "a method that needs the value mutable (`Connection::transaction`, a `Vec`'s `push`) is called through a shared "
        "`&` reference: take `&mut` in the function's parameter and hold the value mutable where it comes from (`let "
        "mut conn = state.db.lock()`), or, for a rusqlite transaction on a shared connection, use "
        "`conn.unchecked_transaction()?`."
    ),
    "couldn't convert the error to `": (
        "`?` turns an error into the function's own error type only where `From` connects them: a function returning "
        "one library's `Result` (`rusqlite::Result`) cannot `?` another's error (`std::io::Error` from creating the "
        "data folder). Return a type both convert into (`Result<T, Box<dyn std::error::Error + Send + Sync>>`), or "
        "do the other work - creating the folder - in a function of its own before this one."
    ),
    "struct import `": (
        "the struct is reached through a module that only imports it with a private `use`: name it from the module "
        "that defines it (and make that `pub`), or re-export it there with `pub use`."
    ),
    "is private: private module": (
        "a test under `tests/` sees only what the crate makes public: declare the module in `src/lib.rs` with "
        "`pub mod <name>;`, not `mod <name>;`."
    ),
    "the `rt-multi-thread` feature": (
        "`#[tokio::main]` needs tokio's `macros` and `rt-multi-thread` features: keep the scaffold's line in "
        "`Cargo.toml`, `tokio = { version = \"1\", features = [\"macros\", \"rt-multi-thread\", \"net\"] }`."
    ),
    "in the crate root": (
        "a module the code names is not declared where the crate starts: every file under `src/` that another uses "
        "must be named once in `src/lib.rs` with `pub mod <name>;` (for `src/<name>.rs`), and `main.rs` reaches it "
        "through the crate's name, never with its own `mod <name>;`."
    ),
    "could not find `test` in `axum`": (
        "axum has no `test` module and no test client: a test sends a request with `tower::ServiceExt::oneshot`, "
        "importing `axum::body::Body`, `axum::http::{Request, StatusCode}`, `http_body_util::BodyExt` and "
        "`tower::ServiceExt`, as `tests/scaffold_smoke.rs` does."
    ),
    "Service<IncomingStream": (
        "`axum::serve` was given a `Router<AppState>`, a router still waiting for its state. Apply the state with "
        "`.with_state(state)` before serving, so the router served is a plain `Router`." + THE_SIGNATURE_DECIDES
    ),
}

#: The pack's golden example (`StackPack.golden_example`), in axum 0.8: state applied inside `app()` with
#: `.with_state`, `State` before the body extractor, path parameters written `{id}` (0.8; `:id` was 0.7), a body
#: rejection answered by the handler, and a test through `oneshot`.
GOLDEN_LIB = r"""use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use axum::extract::rejection::JsonRejection;
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Clone, Serialize, Deserialize)]
pub struct Item {
    pub id: u64,
    pub name: String,
}

#[derive(Deserialize)]
struct NewItem {
    name: Option<String>,
}

/// Shared by every handler: the data file under DATA_DIR and the lock each read-change-write holds.
#[derive(Clone)]
struct AppState {
    file: Arc<PathBuf>,
    lock: Arc<Mutex<()>>,
}

/// Builds the service. `main.rs` starts it; unit tests call it directly.
pub fn app() -> Router {
    let dir = std::env::var("DATA_DIR").unwrap_or_else(|_| "data".into());
    let state = AppState {
        file: Arc::new(PathBuf::from(dir).join("items.json")),
        lock: Arc::new(Mutex::new(())),
    };
    Router::new()
        .route("/health", get(health))
        .route("/items", post(create))
        .route("/items/{id}", get(find))
        .with_state(state)
}

async fn health() -> Json<Value> {
    Json(json!({ "status": "ok" }))
}

fn error(status: StatusCode, message: &str) -> Response {
    (status, Json(json!({ "error": message }))).into_response()
}

fn load(file: &std::path::Path) -> Vec<Item> {
    std::fs::read_to_string(file)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

fn save(file: &std::path::Path, items: &[Item]) -> std::io::Result<()> {
    if let Some(dir) = file.parent() {
        std::fs::create_dir_all(dir)?;
    }
    std::fs::write(file, serde_json::to_string(items)?)
}

// The body extractor is the last argument, after `State`; a body that does not parse is this handler's 400.
async fn create(State(state): State<AppState>, body: Result<Json<NewItem>, JsonRejection>) -> Response {
    let name = match body {
        Ok(Json(NewItem { name: Some(name) })) if !name.trim().is_empty() => name.trim().to_string(),
        _ => return error(StatusCode::BAD_REQUEST, "name is required"),
    };
    let _held = state.lock.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let mut items = load(&state.file);
    let item = Item { id: items.iter().map(|i| i.id).max().unwrap_or(0) + 1, name };
    items.push(item.clone());
    match save(&state.file, &items) {
        Ok(()) => (StatusCode::CREATED, Json(item)).into_response(),
        Err(_) => error(StatusCode::INTERNAL_SERVER_ERROR, "the item could not be stored"),
    }
}

async fn find(State(state): State<AppState>, Path(id): Path<u64>) -> Response {
    let _held = state.lock.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    match load(&state.file).into_iter().find(|item| item.id == id) {
        Some(item) => Json(item).into_response(),
        None => error(StatusCode::NOT_FOUND, "item not found"),
    }
}
"""

GOLDEN_TEST = r"""use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt;

// nextest runs each test in a process of its own, so each sets its own DATA_DIR before building the service.
fn fresh_data_dir(name: &str) {
    let dir = std::env::temp_dir().join(format!("{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::env::set_var("DATA_DIR", &dir);
}

async fn send(request: Request<Body>) -> (StatusCode, Value) {
    let response = {{package}}::app().oneshot(request).await.unwrap();
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    (status, serde_json::from_slice(&bytes).unwrap_or(Value::Null))
}

fn post_json(uri: &str, body: &'static str) -> Request<Body> {
    Request::post(uri)
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap()
}

#[tokio::test]
async fn an_item_is_stored_and_read_back() {
    fresh_data_dir("stored");
    let (status, created) = send(post_json("/items", r#"{"name":"first"}"#)).await;
    assert_eq!(status, StatusCode::CREATED);
    let uri = format!("/items/{}", created["id"]);
    let (status, found) = send(Request::get(uri).body(Body::empty()).unwrap()).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(found["name"], "first");
}

#[tokio::test]
async fn a_missing_name_is_refused_and_an_unknown_id_is_not_found() {
    fresh_data_dir("refused");
    assert_eq!(send(post_json("/items", "{}")).await.0, StatusCode::BAD_REQUEST);
    let (status, _) = send(Request::get("/items/99").body(Body::empty()).unwrap()).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}
"""

PACK = service_pack(
    golden_example={"src/lib.rs": GOLDEN_LIB, "tests/items.rs": GOLDEN_TEST},
    known_errors=AXUM_KNOWN_ERRORS,
    required_signatures={"src/lib.rs": ((r"^\s*pub\s+fn\s+app\s*\(\s*\)\s*->\s*Router\s*\{", "pub fn app() -> Router"),)},
    sandbox_image=sandbox.RUST,
    name="rust-axum-api",
    entrypoint="src/lib.rs",
    title="HTTP service in Rust on axum",
    language="rust",
    frameworks=("axum", "tokio"),
    files={
        "Cargo.toml": CARGO_TOML,
        "src/lib.rs": LIB,
        "src/main.rs": MAIN,
        ".config/nextest.toml": NEXTEST,
        ".cargo/config.toml": CARGO_CONFIG,
    },
    install=(("cargo", "build", "--all-targets"),),
    unit_test=("cargo", "nextest", "run", "--profile", "ci", "--no-fail-fast", "--no-tests=pass"),
    unit_report="target/nextest/ci/junit.xml",
    unit_dir="tests",
    unit_pattern="*.rs",
    start="cargo build && exec ./target/debug/{{package}}",
    server_timeout_ms=600_000,
    smoke_unit=("tests/scaffold_smoke.rs", SMOKE_UNIT),
    guide=GUIDE,
    design_facts=(
        # Measured on Rust runs: `app()` declared `-> Router<AppState>`, which `axum::serve` cannot serve; and the
        # specification planned unit tests on "axum's TestClient", from the model's own memory - the builders' guide
        # says there is no `axum::test`, but the stages writing the specification never read it.
        "`src/lib.rs`'s `pub fn app() -> Router` applies its own state inside with `.with_state(state)`; `main.rs` and "
        "the unit tests use `app()` as it is and never apply state themselves, the tests through "
        "`tower::ServiceExt::oneshot`. Never "
        "`Router<AppState>`: `axum::serve` cannot serve it. axum has no `axum::test` module and no `TestClient`.",
        # Measured on a Rust run: the store's `sqlx::query!` macros needed a database at build time and it never built.
        "With sqlx, queries are `sqlx::query(...).bind(...)` or `query_as::<_, T>(...)`, never the `query!` macros: "
        "those need a live database at build time.",
    ),
    stack={
        "language": "Rust",
        "framework": "axum",
        "frontend_framework": "",
        "testing_framework": "cargo nextest for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(
        "      - uses: dtolnay/rust-toolchain@stable\n"
        "      - uses: taiki-e/install-action@nextest",
    ),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\ntarget/\nacceptance/\ndata/\n"},
    kept_files=(".config/nextest.toml", ".cargo/config.toml"),
    gitignore="target/\n",
)
