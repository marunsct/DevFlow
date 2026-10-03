# Product Brief: Bookmarks

## Overview
A web app for saving links, with its own small HTTP service so the bookmarks are kept on the server.

## Requirements
1. **Features**:
   - Save a bookmark with a title, a URL and an optional tag
   - List saved bookmarks, newest first
   - Delete a bookmark
   - Filter the list by tag
   - Bookmarks are kept by the service and survive a reload of the page
2. **No authentication required**

## Interface
- The service serves the page at `/`.
- The page has a text field labelled "Title", a text field labelled "URL", a text field labelled "Tag" and a button named "Save bookmark".
- A bookmark without a title, or whose URL does not start with `http://` or `https://`, is not saved.
- Each bookmark is an item of a list showing its title as a link to its URL, and its tag. Each has a button named "Delete".
- A text field labelled "Filter by tag" shows only the bookmarks with exactly that tag; when it is empty, all are shown.
- The service's JSON interface:
  - `GET /api/bookmarks` answers 200 with an array of `{"id", "title", "url", "tag"}`, newest first.
  - `POST /api/bookmarks` with `{"title", "url", "tag"}` answers 201 with the bookmark, or 400 or 422 for invalid input, storing nothing.
  - `DELETE /api/bookmarks/{id}` answers 204, or 404 when there is no such bookmark.
- The project directory has a `start.sh` that starts the service on 127.0.0.1 at the port in the `PORT` environment variable, keeping its data under the directory in `DATA_DIR`.

## Technical Constraints
- JavaScript on Node.js

## Acceptance Criteria
- Bookmarks can be saved, listed, filtered and deleted from the page
- The JSON interface behaves as described
- Invalid bookmarks are refused
- The list survives a reload
