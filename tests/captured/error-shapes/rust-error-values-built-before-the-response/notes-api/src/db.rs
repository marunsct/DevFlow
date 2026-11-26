use crate::error::AppError;
use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use sqlx::sqlite::Sqlite;
use sqlx::Pool;

// ============================================================================
// Domain type
// ============================================================================

/// A note stored in the database.
/// Fields: id (auto-generated integer), title (required non-empty string),
/// body (optional string, defaults to empty).
///
/// `FromRow` is derived so that sqlx's builder-style `query_as` can map
/// each column of a SELECT/RETURNING row back into this struct. Column
/// names must match field names (id→id, title→title, body→body).
#[derive(Clone, Debug, Serialize, Deserialize, FromRow)]
pub struct Note {
    pub id: i64,
    pub title: String,
    pub body: String,
}

// ============================================================================
// Database operations
// ============================================================================

/// Ensure the notes table exists in the database.
/// Safe to call on every start via CREATE TABLE IF NOT EXISTS.
/// Does not verify or fail on schema mismatch — CREATE TABLE IF NOT EXISTS
/// handles existing tables gracefully.
pub async fn ensure_schema(pool: &Pool<Sqlite>) -> Result<(), sqlx::Error> {
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT ''
        )",
    )
    .execute(pool)
    .await?;
    Ok(())
}

/// Create a new note in the database within a transaction.
/// Uses RETURNING to obtain the generated id on the same connection that
/// inserted it, avoiding race conditions with MAX(id) + 1.
pub async fn create_note(
    pool: &Pool<Sqlite>,
    title: String,
    body: String,
) -> Result<Note, AppError> {
    let mut tx = pool.begin().await.map_err(|e| {
        AppError::BadRequest(format!("Database error: {}", e))
    })?;

    // query_as::<_, Note>(...) — the second type parameter is the Rust type
    // that maps to each column in the result row.  Sqlite's id maps to i64,
    // title and body map to String.
    let row = sqlx::query_as::<_, Note>(
        "INSERT INTO notes (title, body) VALUES (?, ?) RETURNING id, title, body",
    )
    .bind(&title)
    .bind(&body)
    .fetch_one(&mut *tx)
    .await
    .map_err(|e| AppError::BadRequest(format!("Database error: {}", e)))?;

    tx.commit().await.map_err(|e| {
        AppError::BadRequest(format!("Database error: {}", e))
    })?;

    Ok(row)
}

/// List all notes ordered by ascending id.
pub async fn list_notes(pool: &Pool<Sqlite>) -> Result<Vec<Note>, AppError> {
    let rows = sqlx::query_as::<_, Note>(
        "SELECT id, title, body FROM notes ORDER BY id ASC",
    )
    .fetch_all(pool)
    .await
    .map_err(|e| AppError::BadRequest(format!("Database error: {}", e)))?;
    Ok(rows)
}

/// Fetch a single note by its id.
/// Returns Err(AppError::NotFound(id)) if no row matches.
pub async fn get_note(pool: &Pool<Sqlite>, id: i64) -> Result<Note, AppError> {
    let row = sqlx::query_as::<_, Note>(
        "SELECT id, title, body FROM notes WHERE id = ?",
    )
    .bind(&id)
    .fetch_one(pool)
    .await
    .map_err(|_| AppError::NotFound(id))?;
    Ok(row)
}

/// Update an existing note's title and body within a transaction.
/// Checks existence first, then performs UPDATE ... RETURNING.
/// Returns Err(AppError::NotFound(id)) if no row exists with the given id.
pub async fn update_note(
    pool: &Pool<Sqlite>,
    id: i64,
    title: String,
    body: String,
) -> Result<Note, AppError> {
    let mut tx = pool.begin().await.map_err(|e| {
        AppError::BadRequest(format!("Database error: {}", e))
    })?;

    // Use query (not query_as) since we only need to check existence.
    let existing = sqlx::query("SELECT id FROM notes WHERE id = ?")
        .bind(&id)
        .fetch_optional(&mut *tx)
        .await
        .map_err(|e| AppError::BadRequest(format!("Database error: {}", e)))?;

    if existing.is_none() {
        return Err(AppError::NotFound(id));
    }

    let row = sqlx::query_as::<_, Note>(
        "UPDATE notes SET title = ?, body = ? WHERE id = ? RETURNING id, title, body",
    )
    .bind(&title)
    .bind(&body)
    .bind(&id)
    .fetch_one(&mut *tx)
    .await
    .map_err(|e| AppError::BadRequest(format!("Database error: {}", e)))?;

    tx.commit().await.map_err(|e| {
        AppError::BadRequest(format!("Database error: {}", e))
    })?;

    Ok(row)
}

/// Delete a note by its id within a transaction.
/// Checks existence first, then performs DELETE.
/// Returns Err(AppError::NotFound(id)) if no row exists with the given id.
pub async fn delete_note(pool: &Pool<Sqlite>, id: i64) -> Result<(), AppError> {
    let mut tx = pool.begin().await.map_err(|e| {
        AppError::BadRequest(format!("Database error: {}", e))
    })?;

    // Use query (not query_as) since we only need to check existence.
    let existing = sqlx::query("SELECT id FROM notes WHERE id = ?")
        .bind(&id)
        .fetch_optional(&mut *tx)
        .await
        .map_err(|e| AppError::BadRequest(format!("Database error: {}", e)))?;

    if existing.is_none() {
        return Err(AppError::NotFound(id));
    }

    sqlx::query("DELETE FROM notes WHERE id = ?")
        .bind(&id)
        .execute(&mut *tx)
        .await
        .map_err(|e| AppError::BadRequest(format!("Database error: {}", e)))?;

    tx.commit().await.map_err(|e| {
        AppError::BadRequest(format!("Database error: {}", e))
    })?;

    Ok(())
}
