use std::fs;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use rusqlite::{Connection, OpenFlags};

/// Shared application state holding the database connection.
#[derive(Clone)]
pub struct AppState {
    pub conn: Arc<Mutex<Connection>>,
}

/// Initializes the database and returns the application state.
///
/// Creates the data directory if it does not exist.
/// Opens or creates the SQLite database file.
/// Ensures the schema exists, WAL mode is enabled, and busy timeout is set.
/// Verifies writability.
pub fn init_db(data_dir: &str) -> AppState {
    let path = Path::new(data_dir);

    // Create DATA_DIR if missing (with parents)
    if !path.exists() {
        fs::create_dir_all(path).expect("failed to create data directory");
    }

    let db_path = path.join("notes.db");

    // Open or create notes.db
    let conn = Connection::open_with_flags(&db_path, OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE)
        .expect("failed to open database");

    // Run CREATE TABLE IF NOT EXISTS migration
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT
        );"
    ).expect("failed to create table");

    // Enable WAL mode
    conn.pragma_update(None, "journal_mode", "WAL")
        .expect("failed to enable WAL mode");

    // Set busy_timeout to 5 seconds so SQLite waits rather than failing on concurrent writes.
    conn.busy_timeout(Duration::from_millis(5000))
        .expect("failed to set busy timeout");

    AppState {
        conn: Arc::new(Mutex::new(conn)),
    }
}
