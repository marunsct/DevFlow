## Domain Model
- Note: A record representing a user note. Fields: id (int, auto-generated positive integer, primary key), title (string, required, non-empty after trimming), body (string, optional on input, normalized to empty string if missing). Carried by POST /notes and PUT /notes/{id} endpoints. Exposed in the JSON response interface. Verified by acceptance tests (TS-1 to TS-5) which assert the presence and values of title and body fields in created and updated notes. Stored in SQLite table 'notes' with columns: id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT ''.
- NoteError: A JSON object returned on validation failure (HTTP 400). Fields: title (string, error message describing the validation failure).
- HealthResponse: An empty response body indicating the service is running.

