use axum::http::StatusCode;
use axum::response::{IntoResponse, Json, Response};
use serde_json::json;

/// Application-level error types mapped to HTTP responses.
/// - BadRequest -> 400 Bad Request (malformed JSON)
/// - NotFound   -> 404 Not Found (resource does not exist)
/// - ValidationError -> 422 Unprocessable Entity (invalid input data)
#[derive(Debug)]
pub enum AppError {
    /// Client sent malformed or invalid request body. Returns HTTP 400.
    BadRequest(String),
    /// The requested resource was not found. Returns HTTP 404.
    NotFound(i64),
    /// Input validation failed (e.g., missing title). Returns HTTP 422.
    ValidationError(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        match self {
            // BadRequest: return 400 with a JSON error body {"error": "<message>"}
            AppError::BadRequest(message) => (
                StatusCode::BAD_REQUEST,
                Json(json!({ "error": message })),
            )
                .into_response(),
            // NotFound: return 404 with a JSON error body {"error": "Note not found"}
            AppError::NotFound(_id) => (
                StatusCode::NOT_FOUND,
                Json(json!({ "error": "Note not found" })),
            )
                .into_response(),
            // ValidationError: return 422 with a JSON error body {"error": "<message>"}
            AppError::ValidationError(message) => (
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({ "error": message })),
            )
                .into_response(),
        }
    }
}
