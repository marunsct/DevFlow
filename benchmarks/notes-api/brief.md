# Product Brief: Notes API

## Overview
A small HTTP service that stores short notes for other programs to use.

## Requirements
1. **Features**:
   - Create a note with a title and a body
   - List all notes
   - Fetch one note by its id
   - Update a note's title and body
   - Delete a note
   - Notes survive a restart of the service
2. **No authentication required**

## Interface
- JSON over HTTP. A note is `{"id": <integer>, "title": <string>, "body": <string>}`.
- `POST /notes` with `{"title": ..., "body": ...}` creates a note and answers 201 with the note.
- `GET /notes` answers 200 with a JSON array of every note.
- `GET /notes/{id}` answers 200 with the note, or 404 when there is none.
- `PUT /notes/{id}` with `{"title": ..., "body": ...}` replaces both and answers 200 with the note, or 404.
- `DELETE /notes/{id}` answers 204, or 404.
- A title that is missing or empty is refused with 400 or 422, and nothing is stored.
- `GET /health` answers 200.
- The project directory has a `start.sh` that starts the service on 127.0.0.1 at the port in the `PORT` environment variable, keeping its data under the directory in the `DATA_DIR` environment variable.

## Technical Constraints
- Python
- Data stored in SQLite or a JSON file under `DATA_DIR`

## Acceptance Criteria
- Every operation works as the interface says
- Notes persist across restarts
- Invalid input is refused without storing anything
