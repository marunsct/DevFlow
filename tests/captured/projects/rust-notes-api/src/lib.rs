use axum::{Extension, Router};
use std::env;

mod handlers;
mod models;
mod router;
mod state;

use crate::router::routes;
use crate::state::{init_db, AppState};

/// Builds the service. `main.rs` starts it; unit tests call it directly.
pub fn app() -> Router {
    let data_dir = env::var("DATA_DIR").unwrap_or_else(|_| "data/".to_string());
    let state = init_db(&data_dir);

    routes().with_state(Extension(state))
}
