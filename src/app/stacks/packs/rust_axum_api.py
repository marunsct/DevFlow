"""An HTTP service in Rust, on axum and tokio."""

from __future__ import annotations

from app.stacks.packs._service import service_pack

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

GUIDE = """The service is Rust on axum: `app()` in `src/lib.rs` builds its `Router` (add routes
with `.route("/items", post(create))`), and `src/main.rs` starts it. Unit tests go in
`tests/`, one file per area (`tests/<area>.rs`), calling `{{package}}::app()` with
`tower::ServiceExt::oneshot` - or in a `#[cfg(test)]` module beside the code. Run
them with `cargo nextest run` (or `cargo test`). Add a crate with `cargo add <name>`."""

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

PACK = service_pack(
    name="rust-axum-api",
    title="HTTP service in Rust on axum",
    language="rust",
    frameworks=("axum", "tokio"),
    files={
        "Cargo.toml": CARGO_TOML,
        "src/lib.rs": LIB,
        "src/main.rs": MAIN,
        ".config/nextest.toml": NEXTEST,
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
    kept_files=(".config/nextest.toml",),
    gitignore="target/\n",
)
