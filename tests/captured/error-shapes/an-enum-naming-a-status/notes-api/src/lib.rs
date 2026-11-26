/// Application-level error type converted to HTTP responses.
#[derive(Debug)]
pub enum AppError {
    BadRequest(String),
    NotFound(String),
    InternalServerError,
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
            AppError::InternalServerError => (StatusCode::INTERNAL_SERVER_ERROR, "internal server error".into()),
        };
        let body = serde_json::json!({"error": message});
        (status, axum::Json(body)).into_response()
    }
}

