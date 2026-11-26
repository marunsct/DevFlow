use axum::{
    extract::{Extension, Json, Path},
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde::{Deserialize, Serialize};

use crate::state::AppState;

/// Request body for creating a new note.
#[derive(Deserialize)]
pub struct CreateNoteRequest {
    pub title: String,
    pub body: String,
}

/// Request body for updating an existing note.
#[derive(Deserialize)]
pub struct UpdateNoteRequest {
    pub title: String,
    pub body: String,
}

/// Response object for a note.
#[derive(Serialize)]
pub struct Note {
    pub id: u64,
    pub title: String,
    pub body: Option<String>,
}

/// Error response object.
#[derive(Serialize)]
pub struct ErrorResponse {
    pub error: String,
}

/// Unified response type for all handlers.
///
/// This enum wraps every possible handler return value into a single concrete type
/// that implements `IntoResponse`. It solves the Rust type-inference problem where
/// mixing `(StatusCode, Json<Note>)` and `(StatusCode, Json<ErrorResponse>)` in the
/// same function causes "mismatched types" errors — `impl IntoResponse` requires one
/// concrete return type, not a trait object.
enum AppResponse {
    /// Success with a single note body (201 Created, 200 OK).
    Note(StatusCode, Note),
    /// Success with a list of notes (200 OK for GET /notes).
    List(StatusCode, Vec<Note>),
    /// Error response (4xx / 5xx).
    Error(StatusCode, ErrorResponse),
    /// No content (204 No Content).
    NoContent,
}

impl IntoResponse for AppResponse {
    fn into_response(self) -> Response {
        match self {
            AppResponse::Note(status, note) => (status, Json(note)).into_response(),
            AppResponse::List(status, notes) => (status, Json(notes)).into_response(),
            AppResponse::Error(status, err) => (status, Json(err)).into_response(),
            AppResponse::NoContent => StatusCode::NO_CONTENT.into_response(),
        }
    }
}

/// Validates that the title is non-empty after trimming whitespace.
/// Returns an error tuple (status code + ErrorResponse) if validation fails.
fn validate_title(title: &str) -> Result<(), (StatusCode, ErrorResponse)> {
    if title.trim().is_empty() {
        return Err((
            StatusCode::UNPROCESSABLE_ENTITY,
            ErrorResponse {
                error: "Title must not be empty or whitespace-only".to_string(),
            },
        ));
    }
    Ok(())
}

/// Handler for POST /notes to create a new note.
///
/// Validates the title, inserts into SQLite, and returns the created note.
pub async fn create_handler(
    Extension(state): Extension<AppState>,
    Json(payload): Json<CreateNoteRequest>,
) -> impl IntoResponse {
    // Validate title first
    if let Err((status, err)) = validate_title(&payload.title) {
        return AppResponse::Error(status, err);
    }

    let title = payload.title.trim().to_string();
    let body = Some(payload.body);

    let conn = state.conn.lock().unwrap();

    // Execute INSERT directly (single statement).
    let result = conn.execute(
        "INSERT INTO notes (title, body) VALUES (?1, ?2)",
        rusqlite::params![&title, &body],
    );

    let id: u64 = match result {
        Ok(count) => {
            if count == 0 {
                return AppResponse::Error(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    ErrorResponse { error: "Failed to insert note".to_string() },
                );
            }
            conn.last_insert_rowid() as u64
        }
        Err(e) => {
            // Log the error to stderr so it's visible in the acceptance test output
            tracing::error!("Database error during note creation: {}", e);
            return AppResponse::Error(
                StatusCode::INTERNAL_SERVER_ERROR,
                ErrorResponse { error: "Failed to create note".to_string() },
            );
        }
    };

    let note = Note { id, title, body };
    AppResponse::Note(StatusCode::CREATED, note)
}

/// Handler for GET /notes to list all notes.
pub async fn list_handler(Extension(state): Extension<AppState>) -> impl IntoResponse {
    let conn = state.conn.lock().unwrap();

    let mut stmt = conn.prepare("SELECT id, title, body FROM notes ORDER BY id ASC").unwrap();
    let note_iter = stmt.query_map([], |row| {
        Ok(Note {
            id: row.get(0).unwrap(),
            title: row.get(1).unwrap(),
            body: row.get(2)?,
        })
    }).unwrap();

    let notes: Vec<Note> = note_iter.filter_map(|r| r.ok()).collect();

    // Return an empty array when no notes exist.
    AppResponse::List(StatusCode::OK, notes)
}

/// Handler for GET /notes/{id} to get a specific note.
pub async fn get_handler(
    Extension(state): Extension<AppState>,
    Path(id): Path<u64>,
) -> impl IntoResponse {
    let conn = state.conn.lock().unwrap();

    match conn.query_row(
        "SELECT id, title, body FROM notes WHERE id = ?1",
        rusqlite::params![id],
        |row| {
            Ok(Note {
                id: row.get(0).unwrap(),
                title: row.get(1).unwrap(),
                body: row.get(2)?,
            })
        },
    ) {
        Ok(note) => AppResponse::Note(StatusCode::OK, note),
        Err(rusqlite::Error::QueryReturnedNoRows) => AppResponse::Error(
            StatusCode::NOT_FOUND,
            ErrorResponse { error: format!("Note with id {} not found", id) },
        ),
        Err(e) => {
            tracing::error!("Database error during note fetch: {}", e);
            AppResponse::Error(
                StatusCode::INTERNAL_SERVER_ERROR,
                ErrorResponse { error: "Failed to fetch note".to_string() },
            )
        }
    }
}

/// Handler for PUT /notes/{id} to update a note.
///
/// Validates title, checks existence, updates, and returns the updated note.
pub async fn update_handler(
    Extension(state): Extension<AppState>,
    Path(id): Path<u64>,
    Json(payload): Json<UpdateNoteRequest>,
) -> impl IntoResponse {
    // Validate title first before touching the DB
    if let Err((status, err)) = validate_title(&payload.title) {
        return AppResponse::Error(status, err);
    }

    let title = payload.title.trim().to_string();
    let body = Some(payload.body);

    let conn = state.conn.lock().unwrap();

    // Check if note exists first to provide specific 404 message if needed.
    let exists = conn
        .query_row("SELECT COUNT(*) FROM notes WHERE id = ?", rusqlite::params![id], |row| row.get::<_, i64>(0))
        .unwrap_or(0) > 0;

    if !exists {
        return AppResponse::Error(
            StatusCode::NOT_FOUND,
            ErrorResponse { error: format!("Note with id {} not found", id) },
        );
    }

    // Perform update directly (single statement).
    let result = conn.execute(
        "UPDATE notes SET title = ?1, body = ?2 WHERE id = ?3",
        rusqlite::params![&title, &body, &id],
    );

    match result {
        Ok(count) => {
            if count == 0 {
                // Should not happen since we checked exists above, but handle defensively.
                return AppResponse::Error(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    ErrorResponse { error: "Failed to update note".to_string() },
                );
            }
        }
        Err(e) => {
            tracing::error!("Database error during note update: {}", e);
            return AppResponse::Error(
                StatusCode::INTERNAL_SERVER_ERROR,
                ErrorResponse { error: "Failed to update note".to_string() },
            );
        }
    }

    // Fetch updated note to return it
    let note = conn.query_row(
        "SELECT id, title, body FROM notes WHERE id = ?",
        rusqlite::params![id],
        |row| {
            Ok(Note {
                id: row.get(0).unwrap(),
                title: row.get(1).unwrap(),
                body: row.get(2)?,
            })
        },
    );

    match note {
        Ok(note) => AppResponse::Note(StatusCode::OK, note),
        Err(e) => {
            tracing::error!("Database error during note fetch after update: {}", e);
            AppResponse::Error(
                StatusCode::INTERNAL_SERVER_ERROR,
                ErrorResponse { error: "Failed to fetch updated note".to_string() },
            )
        }
    }
}

/// Handler for DELETE /notes/{id} to delete a note.
pub async fn delete_handler(
    Extension(state): Extension<AppState>,
    Path(id): Path<u64>,
) -> impl IntoResponse {
    let conn = state.conn.lock().unwrap();

    let changes = conn.execute("DELETE FROM notes WHERE id = ?", rusqlite::params![id]);

    let changes_count: usize = match changes {
        Ok(count) => count,
        Err(e) => {
            tracing::error!("Database error during note deletion: {}", e);
            return AppResponse::Error(
                StatusCode::INTERNAL_SERVER_ERROR,
                ErrorResponse { error: "Failed to delete note".to_string() },
            );
        }
    };

    if changes_count == 0 {
        return AppResponse::Error(
            StatusCode::NOT_FOUND,
            ErrorResponse { error: format!("Note with id {} not found", id) },
        );
    }

    AppResponse::NoContent
}
