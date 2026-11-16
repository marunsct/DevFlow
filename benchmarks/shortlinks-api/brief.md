# Product Brief: Short Links

## Overview
A small HTTP service that turns long web addresses into short codes and sends visitors on to the long address.

## Requirements
1. **Features**:
   - Shorten an address, optionally choosing the code
   - Follow a code to its address
   - See how many times a code was followed
   - List every short link
   - Delete a short link
   - Links survive a restart of the service
2. **No authentication required**

## Interface
- JSON over HTTP. A link is `{"code": <string>, "url": <string>, "visits": <integer>}`.
- `POST /links` with `{"url": ...}` creates a link with a code of 6 letters and digits, and answers 201 with the link.
  With `{"url": ..., "code": ...}` it uses that code; a code already taken is refused with 409.
- A `url` that does not start with `http://` or `https://` is refused with 400 or 422, and nothing is stored.
- `GET /links` answers 200 with a JSON array of every link.
- `GET /links/{code}` answers 200 with the link, or 404.
- `GET /r/{code}` answers 302 with the link's address in the `Location` header and counts one visit, or 404.
- `DELETE /links/{code}` answers 204, or 404.
- `GET /health` answers 200.
- The project directory has a `start.sh` that starts the service on 127.0.0.1 at the port in the `PORT` environment
  variable, keeping its data under the directory in the `DATA_DIR` environment variable.

## Technical Constraints
- Python
- Data stored in SQLite or a JSON file under `DATA_DIR`

## Acceptance Criteria
- Every operation works as the interface says
- Links and their visit counts persist across restarts
- Invalid input is refused without storing anything
