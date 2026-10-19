# Product Brief: Tasks API

## Overview
An HTTP service where each person signs up, signs in, and keeps their own list
of things to do. Nobody sees anyone else's list.

## Requirements
1. **Features**:
   - Sign up with a username and a password
   - Sign in, which gives a token for the requests that follow
   - Create an item with a title; it starts not done
   - List your own items
   - Mark one of your items done or not done
   - Delete one of your items
   - Accounts and items survive a restart of the service
2. **Authentication**: every item request needs the token from signing in.

## Interface
- JSON over HTTP. An item is `{"id": <integer>, "title": <string>, "done": <boolean>}`.
- `POST /signup` with `{"username": ..., "password": ...}` answers 201 with `{"username": ...}`, or 409 when the username is taken. A missing or empty username or password is refused with 400 or 422.
- `POST /signin` with `{"username": ..., "password": ...}` answers 200 with `{"token": <string>}`, or 401 when they do not match an account.
- Every request below sends the header `Authorization: Bearer <token>`; without a valid token it answers 401.
- `POST /items` with `{"title": ...}` answers 201 with the item. A missing or empty title is refused with 400 or 422, and nothing is stored.
- `GET /items` answers 200 with a JSON array of the signed-in person's items only.
- `PATCH /items/{id}` with `{"done": true|false}` answers 200 with the item, or 404 when it is not one of the signed-in person's items.
- `DELETE /items/{id}` answers 204, or 404 when it is not one of the signed-in person's items.
- `GET /health` answers 200 without a token.
- The project directory has a `start.sh` that starts the service on 127.0.0.1 at the port in the `PORT` environment variable, keeping its data under the directory in the `DATA_DIR` environment variable. Nothing else is set in its environment: any secret it needs it makes and keeps itself.

## Technical Constraints
- Python
- Data stored in SQLite under `DATA_DIR`
- Passwords are never stored as given

## Acceptance Criteria
- Every operation works as the interface says
- One person's items are never visible to or changeable by another
- Accounts and items persist across restarts, and signing in still works after one
- Invalid input is refused without storing anything
