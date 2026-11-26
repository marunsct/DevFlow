use std::env;
use tokio::net::TcpListener;

/// Entry point for the Notes API binary.
///
/// Reads PORT and DATA_DIR environment variables (with defaults).
/// Initializes the application router and state via `notes_api::app()`.
/// Binds to 127.0.0.1:<PORT> and serves requests until interrupted.
#[tokio::main]
async fn main() {
    let host = std::env::var("HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let port = std::env::var("PORT").unwrap_or_else(|_| "3000".into());

    // Initialize tracing subscriber for structured logging as per spec
    tracing_subscriber::fmt::init();

    let listener = TcpListener::bind(format!("{host}:{port}"))
        .await
        .expect("Failed to bind to address");

    println!("Listening on http://{host}:{port}");

    axum::serve(listener, notes_api::app())
        .await
        .expect("Failed to start server");
}
