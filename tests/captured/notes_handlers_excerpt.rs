    }

    Ok((StatusCode::CREATED, Json(note)))
}

/// List all notes.
///
/// Returns a JSON array of all Note objects ordered by id ascending with status 200.
pub async fn list_notes(State(state): State<AppState>) -> Json<Vec<Note>> {
    let store = state.store.lock().await;
    let notes = store.list_notes();
    drop(store);

    Json(notes)
}

/// Get a note by its ID.
///
/// Returns the Note object with status 200 if found.
/// Returns 404 with an error message if not found.
pub async fn get_note(
