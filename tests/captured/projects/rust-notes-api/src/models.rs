use axum::Json;
use serde::{Deserialize, Serialize};

/// Represents a Note in the system.
/// Contains exactly three fields: id, title, and body.
#[derive(Debug, Clone, Serialize)]
pub struct Note {
    pub id: u64,
    pub title: String,
    pub body: String,
}

/// Request payload for creating a new note (POST /notes).
#[derive(Debug, Deserialize)]
pub struct CreateNoteRequest {
    pub title: String,
    pub body: String,
}

/// Request payload for updating an existing note (PUT /notes/:id).
#[derive(Debug, Deserialize)]
pub struct UpdateNoteRequest {
    pub title: String,
    pub body: String,
}

/// Error response body for 4xx and 5xx errors.
/// Contains exactly one field "error" with a human-readable message.
#[derive(Debug, Serialize)]
pub struct ErrorResponse {
    pub error: String,
}

impl ErrorResponse {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            error: message.into(),
        }
    }
}
