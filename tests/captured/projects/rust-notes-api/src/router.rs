use axum::{routing::{delete, get, post, put}, Extension, Router};
use tower_http::trace::TraceLayer;
use tracing::info;

use crate::handlers::{create_handler, delete_handler, get_handler, list_handler, update_handler};
use crate::state::AppState;

/// Defines and mounts all route handlers for the Notes API.
///
/// Mounts:
/// - POST /notes (create_handler)
/// - GET /notes (list_handler)
/// - GET /notes/:id (get_handler)
/// - PUT /notes/:id (update_handler)
/// - DELETE /notes/:id (delete_handler)
/// - GET /health (health_handler)
///
/// Returns an axum::Router configured with these endpoints and wrapped in AppState.
pub fn routes() -> Router<Extension<AppState>> {
    Router::new()
        .route("/notes", post(create_handler).get(list_handler))
        .route("/notes/{id}", get(get_handler).put(update_handler).delete(delete_handler))
        .route("/health", get(health_handler))
        .layer(TraceLayer::new_for_http())
}

/// Health check endpoint.
///
/// Returns 200 with a JSON body confirming service readiness.
async fn health_handler() -> axum::Json<serde_json::Value> {
    info!("Health check requested");
    axum::Json(serde_json::json!({"status": "ok"}))
}
