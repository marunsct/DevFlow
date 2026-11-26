# Technical Specification — Notes API
## Product Scope
A lightweight HTTP API that stores short notes with full CRUD operations (create, list, fetch, update, delete). Notes persist across service restarts in a JSON file under DATA_DIR. No authentication layer is included. The service starts via start.sh on 127.0.0.1 at the port from PORT environment variable.

Deferred: authentication and authorization, pagination/filtering/search, rich text or attachments in body, tags/categories/metadata, rate limiting/request throttling, API versioning.

## Component Boundaries
- src/app.ts — Hono application factory. Exports createApp(dataDir?: string): Hono. Registers all routes (POST /notes, GET /notes, GET /notes/:id, PUT /notes/:id, DELETE /notes/:id, GET /health), input validation middleware, and the notFound handler. Reads dataDir from argument or DATA_DIR env var.
- src/storage.ts — JSON file persistence layer. Exports loadNotes(dataDir: string): Note[], saveNotes(notes: Note[], dataDir: string): void, getNextId(notes: Note[]): number. Uses fs module to read/write notes.json under DATA_DIR with atomic writes (write to temp file then rename).
- src/validation.ts — Input validation logic. Exports validateCreateNote(body: unknown): { title: string; body: string } | null and validateUpdateNote(body: unknown): { title: string; body: string } | null. Returns null on failure (caller returns 400/422), validated object on success.
- src/main.ts — Entry point. Imports createApp from app.ts, starts the server with @hono/node-server serve(). Already written by harness; specification does not modify it beyond what is needed for the import to resolve.

## Domain Model
- Note: An object representing a single note with three fields: id (positive integer, auto-incrementing starting from 1), title (string, non-empty after trimming whitespace), body (string, can be empty).
- Notes Store: A JSON array of Note objects persisted in a single file named 'notes.json' under the directory specified by the DATA_DIR environment variable.
- Data Directory: The base directory for storage, specified by the DATA_DIR environment variable. Must exist and be writable; created with parents if missing at startup by the service.

## API and Event Contracts
- POST /notes — Request body: JSON object with 'title' (string, non-empty after trim) and 'body' (string). Response: 201 Created with JSON note object {id, title, body}. Returns 400 Bad Request with {error: string} if title is missing, empty after trim, or request body is not valid JSON.
- GET /notes — No request body. Response: 200 OK with JSON array of all notes sorted by ascending id. Returns empty array [] when no notes exist.
- GET /notes/:id — Path parameter :id parsed as integer. Response: 200 OK with JSON note object if found. Returns 400 Bad Request with {error: string} if :id is not a valid integer. Returns 404 Not Found with {error: string} if no note exists with that id.
- PUT /notes/:id — Path parameter :id parsed as integer. Request body: JSON object requiring both 'title' (string, non-empty after trim) and 'body' (string). Response: 200 OK with updated JSON note object if found. Returns 400 Bad Request with {error: string} if either field is missing or title is empty after trim. Returns 404 Not Found with {error: string} if no note exists with that id.
- DELETE /notes/:id — Path parameter :id parsed as integer. Response: 204 No Content on success (empty response body). Returns 400 Bad Request with {error: string} if :id is not a valid integer. Returns 404 Not Found with {error: string} if no note exists with that id.
- GET /health — No request body. Response: 200 OK with JSON body {status: 'ok'}.

## Data Flows
- Startup Flow: The service reads DATA_DIR from environment variables. It ensures the directory exists. It attempts to read 'notes.json' from DATA_DIR. If the file is missing or empty, it initializes an in-memory store as an empty array. If the file contains malformed JSON, it logs an error and exits. If valid, it parses the JSON array into memory.
- Validation Flow: On POST /notes or PUT /notes/:id, the request body is parsed as JSON. The validateCreateNote or validateUpdateNote function checks that title is present, a string, and non-empty after trimming whitespace. For PUT, body must also be present as a string. If validation fails, no data is written to disk, and a 400/422 response is returned immediately.
- Create Flow (POST /notes): After validation passes, the storage module calculates the next ID by finding the maximum existing ID in the store and adding one (starting at 1 if empty). A new Note object is created with this ID, title, and body. The updated array is written atomically to 'notes.json' using a temp file and fs.rename.
- List Flow (GET /notes): The storage module returns the current in-memory array of notes. The response handler sorts the array by id in ascending order before sending the JSON response.
- Fetch Flow (GET /notes/:id): The path parameter :id is parsed as an integer. If not a valid integer, a 400 error is returned. The store is searched for a note with that exact id. If found, it is returned as 200 OK. If not found, a 404 Not Found response is returned.
- Update Flow (PUT /notes/:id): After validation passes, the path parameter :id is parsed as an integer. If not valid, a 400 error is returned. The store is searched for a note with that id. If found, its title and body are replaced with the validated values. The updated array is written atomically to 'notes.json'. The updated note is returned as 200 OK. If the note is not found, a 404 Not Found response is returned.
- Delete Flow (DELETE /notes/:id): The path parameter :id is parsed as an integer. If not valid, a 400 error is returned. The store is searched for a note with that id. If found, it is removed from the array. The updated array is written atomically to 'notes.json'. A 204 No Content response is returned. If the note is not found, a 404 Not Found response is returned.
- Shutdown Flow: On SIGTERM or SIGINT, the server stops accepting new connections. Any in-flight requests are completed. The process exits gracefully.

## Security and Privacy
- No authentication or authorization is implemented; the API is intended for internal or trusted programmatic consumers only.
- All responses include Content-Type: application/json header via Hono's c.json() helper to ensure proper encoding and escaping.
- Error responses never include stack traces, file paths, internal error messages, or database details; they return a generic JSON object with only an HTTP status code and a user-facing message.
- Console logging must never write raw request bodies or response bodies to stdout; if logging payloads for debugging, truncate them to 256 characters and mask sensitive data fields.
- Atomic file writes are used for all mutations (write to temp file then fs.rename) to prevent data corruption if the process crashes mid-write.
- DATA_DIR environment variable is validated at startup: created if it does not exist, verified as writable, and the service exits with a clear error if access is denied.

## Reliability and Observability
- GET /health returns 200 OK with JSON body { "status": "ok" } to indicate service liveness.
- On startup, if the data file does not exist or is empty, the in-memory store is initialized as an empty array.
- On startup, stored data is validated against the expected schema (id: integer, title: string, body: string); non-conforming records are stripped or coerced to maintain internal consistency, and corrupted files result in starting with an empty store rather than crashing.
- The service handles SIGTERM and SIGINT signals gracefully, stopping acceptance of new connections and completing any in-flight write operations before exiting.
- Notes are persisted to disk after every mutation (POST, PUT, DELETE) using atomic writes to ensure crash safety.
- The service binds to 127.0.0.1 by default and listens on the port specified by the PORT environment variable (defaulting to 3000).

## Testing
- Unit tests use node:test (import test from 'node:test'; import assert from 'node:assert') for modules in notes-api/test/ (*.test.ts).
- Acceptance tests use Playwright (@playwright/test) with the request fixture for HTTP calls against the running service in notes-api/acceptance/ (*.spec.js).
- npm test runs unit tests; npm run test:acceptance runs acceptance tests.
- The acceptance suite starts the service via start.sh and waits until GET /health returns 200 before executing any test.
- Unit tests verify storage module (loadNotes, saveNotes, getNextId) and validation logic (validateCreateNote, validateUpdateNote) using plain objects without a server.
- Acceptance tests use distinct test sub-blocks for separate assertions and ensure each test starts with an empty store by deleting notes.json in setup hooks.
- Tests assert specific HTTP status codes, response body shapes (JSON arrays or objects), Content-Type headers (application/json), and error message formats ({error: string}).
- No other test runners are used; the specification names only node:test and Playwright.

## Deployment
- The service is started via notes-api/start.sh which executes 'cd "$(dirname "$0")" && exec node src/main.ts'.
- The server binds to hostname 127.0.0.1 and port specified by the PORT environment variable (defaulting to 3000 if unset).
- Data is stored in the directory specified by the DATA_DIR environment variable; this directory must be writable.
- The data file is notes-api/<DATA_DIR>/notes.json.
- The service creates the DATA_DIR directory with its parents if it does not exist before writing any data.
- The service runs as a single Node.js process; no concurrent write locking is needed.
- No authentication or authorization layers are deployed.
- Graceful shutdown handling for SIGTERM and SIGINT ensures in-flight writes complete before exit.

## Acceptance Criteria
- AC-1: POST /notes creates a note and returns 201 with the created note object including an integer id.
- AC-2: GET /notes returns 200 with a JSON array of all notes sorted by ascending id.
- AC-3: GET /notes/:id returns 200 with the note if found, or 404 if not found.
- AC-4: PUT /notes/:id replaces both title and body, returns 200 if found, or 404 if not found.
- AC-5: DELETE /notes/:id returns 204 No Content if found, or 404 if not found.
- AC-6: Notes persist across service restarts when using the same DATA_DIR.
- AC-7: Note JSON schema is strictly {"id": integer, "title": string, "body": string} with no extra keys.
- AC-8: POST /notes returns status 201 and Content-Type application/json.
- AC-9: GET /notes returns status 200, Content-Type application/json, and a JSON array body.
- AC-10: GET /notes/:id returns 404 for non-existent ids.
- AC-11: Whitespace-only titles are rejected with 400 or 422 and no data is stored.
- AC-12: PUT requests missing either title or body are rejected with 400 or 422.
- AC-13: Data file is written atomically to prevent corruption on crash.
- AC-16: Full CRUD lifecycle works correctly in sequence.
- AC-17: Persistence is verified by AC-6.
- AC-18: Various validation edge cases (empty, missing, whitespace) for titles are handled correctly.

## Interface Design
- Declined: The product is an HTTP API with no frontend user interface, phone layout, desktop layout, visual style, or accessibility requirements for a person to use directly. The 'interface' refers to the HTTP contract.

## Interface Contract
- AC-1 POST /notes -> 201
- AC-1 POST /notes -> 400 or 422
- AC-2 GET /notes -> 200
- AC-3 GET /notes/:id -> 200
- AC-3 GET /notes/:id -> 404
- AC-3 GET /notes/:id -> 400
- AC-4 PUT /notes/:id -> 200
- AC-4 PUT /notes/:id -> 404
- AC-4 PUT /notes/:id -> 400 or 422
- AC-5 DELETE /notes/:id -> 204
- AC-5 DELETE /notes/:id -> 404
- AC-5 DELETE /notes/:id -> 400
- AC-6 GET /health -> 200

## File Plan
- notes-api/src/app.ts — Hono application setup and route definitions. Exports createApp(dataDir?: string): Hono. Imports { loadNotes, saveNotes, getNextId } from './storage' and { validateCreateNote, validateUpdateNote } from './validation'. Defines all routes: POST /notes, GET /notes, GET /notes/:id, PUT /notes/:id, DELETE /notes/:id, GET /health. Registers notFound handler returning 404 JSON. Creates DATA_DIR directory with parents if missing at startup.
- notes-api/src/storage.ts — JSON file persistence module. Exports loadNotes(dataDir: string): Note[], saveNotes(notes: Note[], dataDir: string): void, getNextId(notes: Note[]): number. Uses fs.readFileSync and fs.writeFileSync for I/O. On read: handles missing file (returns []), empty file (returns []), malformed JSON (throws Error with message 'Invalid data file'). On write: uses atomic rename via temp file.
- notes-api/src/validation.ts — Input validation module. Exports validateCreateNote(body: unknown): { title: string; body: string } | null and validateUpdateNote(body: unknown): { title: string; body: string } | null. Checks that body is an object, title is a non-empty string after trim, and body field is a string (for create) or both fields present (for update). Returns validated object or null.
- notes-api/src/main.ts — Entry point file. Already written by harness. Imports createApp from './app.ts', calls it with DATA_DIR env var, starts server via @hono/node-server serve() on 127.0.0.1 at PORT (default 3000). Specification does not change this file beyond ensuring imports resolve.
- notes-api/start.sh — Shell script entry point. Already written by harness. Runs 'cd "$(dirname "$0")" && exec node src/main.ts'. Specification keeps it as-is.
- notes-api/package.json — npm manifest with type: module, dependencies (hono, @hono/node-server), devDependencies (typescript, node:test runner, playwright), and scripts (test, test:acceptance). Already written by harness; specification does not modify it.
- notes-api/tsconfig.json — TypeScript compiler configuration. Already written by harness.
- notes-api/playwright.config.js — Playwright configuration for acceptance tests. Already written by harness.
- notes-api/acceptance/service.cjs — Acceptance test service starter. Already written by harness.
- notes-api/test/storage.test.ts — Unit tests for storage module using node:test. Tests loadNotes, saveNotes, getNextId with plain objects (no server).
- notes-api/test/validation.test.ts — Unit tests for validation module using node:test. Tests validateCreateNote and validateUpdateNote with various invalid inputs.

## Function Contracts
- File: src/app.ts | Function: createApp(dataDir?: string): Hono | Description: Factory function that creates and configures the Hono application instance. It reads dataDir from the argument or DATA_DIR environment variable. It registers all routes (POST /notes, GET /notes, GET /notes/:id, PUT /notes/:id, DELETE /notes/:id, GET /health), input validation middleware, and a notFound handler. Returns: Hono application instance.
- File: src/storage.ts | Function: loadNotes(dataDir: string): Note[] | Description: Reads the notes.json file from dataDir. If the file does not exist or is empty, returns an empty array []. If the file contains malformed JSON, throws an Error with message 'Invalid data file'. Parses valid JSON into an array of Note objects. Validates and strips unknown fields to ensure schema compliance. Returns: Array of Note objects.
- File: src/storage.ts | Function: saveNotes(notes: Note[], dataDir: string): void | Description: Writes the notes array to a temporary file in dataDir, then atomically renames it to 'notes.json' using fs.rename. This ensures crash safety. Returns: void.
- File: src/storage.ts | Function: getNextId(notes: Note[]): number | Description: Calculates the next available ID by finding the maximum id in the notes array and adding one. If the array is empty, returns 1. Returns: Integer representing the next ID.
- File: src/validation.ts | Function: validateCreateNote(body: unknown): { title: string; body: string } | null | Description: Validates that body is an object with a 'title' (non-empty string after trim) and 'body' (string). Returns validated object if valid, null otherwise.
- File: src/validation.ts | Function: validateUpdateNote(body: unknown): { title: string; body: string } | null | Description: Validates that body is an object with both 'title' (non-empty string after trim) and 'body' (string) fields present. Returns validated object if valid, null otherwise.
- File: src/app.ts | Route: POST /notes | Contract: Accepts JSON body with title and body. Content-Type must be application/json. Validates input using validateCreateNote. If invalid, returns 400 Bad Request with {error: string}. If valid, creates note via storage, saves atomically, returns 201 Created with the new Note object.
- File: src/app.ts | Route: GET /notes | Contract: Returns 200 OK with JSON array of all notes sorted by ascending id. Returns empty array [] if no notes exist.
- File: src/app.ts | Route: GET /notes/:id | Contract: Parses :id as integer. If invalid, returns 400 Bad Request with {error: string}. Fetches note from storage. If found, returns 200 OK with Note object. If not found, returns 404 Not Found with {error: string}.
- File: src/app.ts | Route: PUT /notes/:id | Contract: Parses :id as integer. If invalid, returns 400 Bad Request with {error: string}. Validates input using validateUpdateNote. If invalid, returns 400/422 Bad Request with {error: string} without modifying data. Fetches note from storage. If not found, returns 404 Not Found with {error: string}. If found, updates title and body, saves atomically, returns 200 OK with updated Note object.
- File: src/app.ts | Route: DELETE /notes/:id | Contract: Parses :id as integer. If invalid, returns 400 Bad Request with {error: string}. Fetches note from storage. If not found, returns 404 Not Found with {error: string}. If found, deletes note, saves atomically, returns 204 No Content.
- File: src/app.ts | Route: GET /health | Contract: Returns 200 OK with JSON body {status: 'ok'}.

## Data Contracts
- Note: id is a positive integer (auto-incrementing starting from 1), title is a non-empty string after trimming whitespace, body is a string. Example: {"id": 1, "title": "Meeting notes", "body": "Discuss Q4 roadmap"}

## Error Catalogue
- Invalid JSON body in POST /notes or PUT /notes/:id: Return 400 Bad Request with { "error": "Invalid JSON" }. No data is persisted.
- Missing title field in POST /notes request body: Return 400 Bad Request with { "error": "Title is required" }. No data is persisted.
- Empty or whitespace-only title in POST /notes request body: Return 400 Bad Request with { "error": "Title cannot be empty" }. No data is persisted.
- Missing 'title' or 'body' field in PUT /notes/:id request body: Return 400 Bad Request with { "error": "Both title and body are required" }. No existing note is modified.
- Empty or whitespace-only title in PUT /notes/:id request body: Return 400 Bad Request with { "error": "Title cannot be empty" }. No existing note is modified.
- Note not found for GET /notes/:id where :id is a valid integer: Return 404 Not Found with { "error": "Note not found" }.
- Note not found for PUT /notes/:id where :id is a valid integer: Return 404 Not Found with { "error": "Note not found" }. No existing note is modified.
- Note not found for DELETE /notes/:id where :id is a valid integer: Return 404 Not Found with { "error": "Note not found" }.
- Invalid integer format for :id path parameter in GET, PUT, or DELETE /notes/:id: Return 400 Bad Request with { "error": "Invalid ID format" }.
- Data file contains malformed JSON on startup: Service fails to start and logs a clear error message. No service response is served.

## Implementation Order
- Step 1: Create src/storage.ts. Implement loadNotes, saveNotes, and getNextId functions. Write unit tests in test/storage.test.ts to verify loading empty/valid files, error on malformed JSON, atomic write behavior (simulated), and ID generation logic. Run npm test.
- Step 2: Create src/validation.ts. Implement validateCreateNote and validateUpdateNote. Write unit tests in test/validation.test.ts to cover valid inputs, missing title, empty title, whitespace-only title, missing body on PUT, and invalid types. Run npm test.
- Step 3: Create src/app.ts. Implement createApp function. Register GET /health route returning 200 with {status: 'ok'}. Write acceptance test in acceptance/health.spec.js to verify health check response. Run npm run test:acceptance.
- Step 4: Add POST /notes route to src/app.ts. Use validation and storage modules. Return 201 on success, 400/422 on validation failure. Write acceptance tests in acceptance/create-note.spec.js to verify creation, ID assignment, and validation errors. Run npm run test:acceptance.
- Step 5: Add GET /notes route to src/app.ts. Return sorted array of notes. Write acceptance tests in acceptance/list-notes.spec.js to verify empty list and list after creation. Run npm run test:acceptance.
- Step 6: Add GET /notes/:id route to src/app.ts. Handle integer parsing, 400 for invalid ID, 404 for missing note. Write acceptance tests in acceptance/fetch-note.spec.js. Run npm run test:acceptance.
- Step 7: Add PUT /notes/:id route to src/app.ts. Use validation and storage modules. Return 200 on success, 400/422 on validation failure, 404 if not found. Write acceptance tests in acceptance/update-note.spec.js. Run npm run test:acceptance.
- Step 8: Add DELETE /notes/:id route to src/app.ts. Return 204 on success, 404 if not found. Write acceptance tests in acceptance/delete-note.spec.js. Run npm run test:acceptance.
- Step 9: Implement persistence verification. Write acceptance test in acceptance/persistence.spec.js to create a note, restart service, and verify note survives. Run npm run test:acceptance.
- Step 10: Add integration lifecycle test in acceptance/integration.spec.js covering full CRUD sequence. Verify error response format (BE-8) and Content-Type headers (SR-10) across all tests. Final verification with npm run test:acceptance.

## Test Cases
- AC-1 Create a note: Setup: Empty DATA_DIR. Steps: POST /notes with {"title": "Test", "body": "Content"}. Assertions: Status 201, response JSON has id (integer), title "Test", body "Content".
- AC-2 List all notes: Setup: Empty DATA_DIR. Steps: GET /notes. Assertions: Status 200, body is []. Then POST /notes with {"title": "A", "body": "B"}. Then GET /notes. Assertions: Status 200, array length 1, object matches created note.
- AC-3 Fetch one note by its id: Setup: Create note via POST, capture id. Steps: GET /notes/{id}. Assertions: Status 200, body matches title/body. Then GET /notes/9999 on empty store. Assertions: Status 404.
- AC-4 Update a note: Setup: Create note, capture id. Steps: PUT /notes/{id} with {"title": "Updated", "body": "New body"}. Assertions: Status 200, response has new title/body. Then PUT /notes/9999. Assertions: Status 404.
- AC-5 Delete a note: Setup: Create note, capture id. Steps: DELETE /notes/{id}. Assertions: Status 204, empty body. Then GET /notes/{id}. Assertions: Status 404.
- AC-6 Notes survive restart: Setup: Start service with known DATA_DIR. Steps: POST /notes to create note, capture id. Stop server. Restart service with same DATA_DIR. GET /notes/{id}. Assertions: Status 200, title/body intact.
- AC-7 Note JSON schema: Setup: Create note via POST. Assertions: response.id is number/integer, response.title is string, response.body is string, no extra keys present.
- AC-8 POST /notes creates with 201: Setup: Empty store. Steps: POST /notes with valid body. Assertions: Status exactly 201, Content-Type application/json, response is single object not array.
- AC-9 GET /notes returns JSON array: Setup: Create multiple notes. Steps: GET /notes. Assertions: Status 200, Content-Type application/json, parsed body is Array, length matches count of created notes.
- AC-10 GET /notes/{id} returns 200 or 404: Setup: Create note, capture id. Steps: GET /notes/{id}. Assertions: Status 200, full object. Then GET /notes/9999. Assertions: Status 404.
- AC-11 Whitespace-only title rejection: Setup: Empty store. Steps: POST /notes with {"title": " ", "body": "x"}. Assertions: Status 400 or 422, no note stored (GET /notes is []). Repeat with missing title field.
- AC-12 PUT requires both fields: Setup: Create note. Steps: PUT /notes/{id} with {"title": "New"} (missing body). Assertions: Status 400 or 422, note unchanged. Repeat with missing title.
- AC-13 Atomic write persistence: Setup: Write data. Steps: Kill server during write? (Note: Single process assumption makes crash simulation hard in tests; rely on AC-6 for restart persistence). Assertions: AC-6 covers persistence.
- AC-16 Full lifecycle integration: Setup: Empty store. Steps: Create A, Create B. GET /notes (assert 2 items, ascending id). GET /notes/{A.id} (assert A). PUT /notes/{A.id} (update A). GET /notes/{A.id} (assert updated A). DELETE /notes/{B.id} (assert 204). GET /notes (assert only A remains).
- AC-17 Persistence covered by AC-6.
- AC-18 Validation edge cases: Setup: Empty store. Steps: POST with empty title, whitespace title, missing title. Assertions: All return 400/422, GET /notes remains [].

## Configuration
- PORT: The port number the service listens on. Default: 3000. Type: integer.
- DATA_DIR: The directory path where notes.json is stored. Required: Yes. If missing, the service exits with a clear error message.
- HOST: The hostname the service binds to. Default: 127.0.0.1.
- hono@4.13.18: The Hono web framework used for routing and request handling.
- @hono/node-server@2.1.8: The Node.js server adapter for Hono.
- node:test: The built-in Node.js unit test runner, used for *.test.ts files in notes-api/test/.
- @playwright/test: The acceptance test runner, used for *.spec.js files in notes-api/acceptance/.

## Library Usage
- hono@4.13.18: import { Hono } from 'hono'; const app = new Hono(); — Creates the Hono application instance for routing HTTP requests.
- @hono/node-server@2.1.8: import { serve } from '@hono/node-server'; serve({ fetch: app.fetch, port, hostname }, callback); — Starts an HTTP server on the specified hostname and port using Node.js built-in http module via @hono/node-server adapter.
- fs (Node.js built-in): import * as fs from 'node:fs'; import * as path from 'node:path'; — Reads notes.json with fs.readFileSync(path.join(dataDir, 'notes.json'), 'utf-8') and writes with fs.writeFileSync for non-atomic saves or fs.rename for atomic persistence.
- node:test (built into Node.js): import test from 'node:test'; import assert from 'node:assert'; — Unit test runner for *.test.ts files in notes-api/test/. No install required.
- @playwright/test (devDependency): import { test, expect } from '@playwright/test'; — Acceptance test runner for *.spec.js files in notes-api/acceptance/. Sends HTTP requests against the running service.

## Specialist Advice and Decisions
- DB-1: adopted - storage implementation details
- DB-2: declined - The brief only mandates title validation; body can be empty/omitted on create, and PUT requires both but schema enforcement is handled separately.
- DB-3: adopted - storage logic
- DB-4: adopted - validation logic
- DB-5: adopted - storage startup behavior
- DB-6: adopted - storage persistence mechanism
- DB-7: adopted - data resilience strategy
- DB-8: adopted - data integrity check
- DB-9: adopted - sorting logic
- DB-10: adopted - PUT validation requirement
- BE-1: adopted - POST endpoint behavior
- BE-2: adopted - GET /notes behavior
- BE-3: adopted - GET /notes/:id behavior
- BE-4: adopted - PUT /notes/:id behavior
- BE-5: adopted - DELETE /notes/:id behavior
- BE-6: adopted - Health check response
- BE-7: declined - The brief does not state length limits. Adding character constraints is an added constraint not in scope.
- BE-8: adopted - Error response format
- BE-9: adopted - Storage summary
- BE-10: adopted - Environment variable handling
- SR-1: adopted - Atomic writes
- SR-2: adopted - Validation timing
- SR-3: declined - The brief does not mandate rejecting non-JSON Content-Type with 415. It is an added constraint for MVP.
- SR-4: declined - The brief does not state a request body size limit. Adding a 1MB limit is an added constraint.
- SR-5: adopted - Security best practice for error messages
- SR-6: adopted - Security best practice for logging
- SR-7: adopted - DATA_DIR validation
- SR-8: adopted - Graceful shutdown
- SR-9: adopted - Data corruption handling
- SR-10: adopted - Content-Type header consistency
- TS-1: adopted - Test case AC-1
- TS-2: adopted - Test case AC-2
- TS-3: adopted - Test case AC-3
- TS-4: adopted - Test case AC-4
- TS-5: adopted - Test case AC-5
- TS-6: adopted - Test case AC-6
- TS-7: adopted - Test case AC-7
- TS-8: adopted - Test case AC-8
- TS-9: adopted - Test case AC-9
- TS-10: adopted - Test case AC-10 and additional context

## Open Questions
- Should whitespace-only titles be treated as empty? -> assumed: yes, whitespace-only titles are rejected as empty
- How are note IDs generated? -> assumed: auto-incrementing integers starting from 1
- What order should GET /notes return notes in? -> assumed: ascending by ID
- Are both title and body required on PUT requests? -> assumed: yes, both fields must be present
- Which storage backend for MVP — JSON file or SQLite? -> assumed: JSON file under DATA_DIR for simplicity

## Decisions (ADR)

### ADR-01 — JSON file storage for MVP
**Context:**
The brief allows JSON file or SQLite under DATA_DIR. The service is single-process with no concurrent write locking needed.

**Alternatives:**
- SQLite via better-sqlite3
- Other embedded databases

**Decision:**
Use a single JSON file (notes.json) under DATA_DIR, loaded entirely into memory on startup and rewritten on every mutation.

**Rationale:**
MVP simplicity — zero external dependencies, one file to manage. Atomic writes (temp file + rename) provide crash safety sufficient for single-process use. Matches the intake's assumption for MVP.

**Trade-offs:**
- Not suitable for concurrent writers or very large datasets

**Consequences:**
- Storage module uses fs.readFileSync/fs.writeFileSync
- On restart, entire dataset loaded into memory

**Validation evidence:**
DB-1 adopted; storage tests verify load/save round-trip with plain objects.

### ADR-02 — Auto-incrementing integer IDs starting from 1
**Context:**
The brief specifies note id as <integer> but does not specify how IDs are generated.

**Alternatives:**
- UUID strings
- Timestamp-based IDs
- Random UUIDs

**Decision:**
IDs are auto-incrementing integers starting from 1. On startup, nextId = max(existing ids) + 1, or 1 if no notes exist.

**Rationale:**
Simple, deterministic, matches the brief's integer type. Ascending order in GET /notes responses naturally follows this scheme.

**Trade-offs:**
- IDs are predictable; not suitable where ID secrecy matters
- Gaps possible if deletes occur

**Consequences:**
- getNextId() function in storage.ts tracks max id
- Tests verify sequential IDs after multiple creates

**Validation evidence:**
Open question resolved: auto-incrementing integers starting from 1.

### ADR-03 — Whitespace-only titles rejected as empty
**Context:**
The brief says a title that is missing or empty is refused. It does not explicitly address whitespace-only strings.

**Alternatives:**
- Accept whitespace-only titles
- Trim and accept if non-empty after trim

**Decision:**
Titles consisting only of whitespace (after .trim()) are treated as empty and rejected with 400/422.

**Rationale:**
A whitespace-only title provides no useful content. The open question was resolved: yes, reject whitespace-only titles.

**Trade-offs:**
- User cannot create a note with only spaces as title

**Consequences:**
- validateCreateNote and validateUpdateNote call .trim() on title before checking length

**Validation evidence:**
Open question resolved; acceptance test TS-10 covers whitespace-only title rejection.

### ADR-04 — Ascending ID order for GET /notes
**Context:**
The brief does not specify ordering for the list endpoint.

**Alternatives:**
- Descending by id
- Insertion order (which happens to be ascending)
- No guaranteed order

**Decision:**
Notes are returned sorted by ascending id in GET /notes responses.

**Rationale:**
Deterministic ordering ensures consistent test behavior across restarts. Ascending by id is the most natural and predictable sort for a simple list.

**Trade-offs:**
- Requires sorting on every read if IDs are not naturally ordered (unlikely with auto-increment)

**Consequences:**
- GET /notes handler sorts notes array before returning

**Validation evidence:**
Open question resolved; acceptance test TS-2 verifies ascending order.

### ADR-05 — Both title and body required on PUT
**Context:**
The brief says PUT 'replaces both' title and body. It does not explicitly state whether both fields are required in the request.

**Alternatives:**
- Allow partial updates (only one field)
- Make body optional on PUT

**Decision:**
PUT /notes/:id requires both title and body fields in the request body. Missing either field returns 400/422.

**Rationale:**
'Replaces both' implies the caller must provide both values. Allowing partial updates would require a different semantics (PATCH), which is not in scope.

**Trade-offs:**
- Cannot update only title or only body in a single request

**Consequences:**
- validateUpdateNote checks presence of both fields before proceeding

**Validation evidence:**
Open question resolved; DB-10 adopted.

### ADR-06 — Error response format
**Context:**
The brief specifies status codes but not the shape of error response bodies.

**Alternatives:**
- Plain text error messages
- Multiple possible field names for error message
- No error body (just status)

**Decision:**
All error responses (400, 404, 500) return JSON with a single 'error' field containing a human-readable description. Example: {"error": "Note not found"}.

**Rationale:**
Consistent machine-parseable format for all errors. Matches the pattern used in Hono's c.json() responses.

**Trade-offs:**
- Single error field means only one error per response (no validation error lists)

**Consequences:**
- Every route handler returns c.json({error: 'message'}, status) on failure

**Validation evidence:**
BE-8 adopted; acceptance tests assert error field presence.

<!-- Generated from the architect's structured specification. Editing this file does not change what the pipeline reads. -->
