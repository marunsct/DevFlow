package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"notes-api/store"
)

// NewRouter creates the HTTP handler with all registered routes.
func NewRouter(s *store.Store) *http.ServeMux {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", healthHandler)
	mux.HandleFunc("GET /notes", listHandler(s))
	mux.HandleFunc("POST /notes", createHandler(s))
	mux.HandleFunc("GET /notes/{id}", getHandler(s))
	mux.HandleFunc("PUT /notes/{id}", updateHandler(s))
	mux.HandleFunc("DELETE /notes/{id}", deleteHandler(s))

	return mux
}

// healthHandler returns a JSON health check response with status field.
func healthHandler(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// listHandler returns a handler that lists all notes.
func listHandler(s *store.Store) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		notes := s.GetNotes()
		if notes == nil {
			notes = []store.Note{}
		}

		data, err := json.MarshalIndent(notes, "", "  ")
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}

		w.WriteHeader(http.StatusOK)
		w.Write(data)
	}
}

// createHandler returns a handler that creates a new note.
func createHandler(s *store.Store) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		var req struct {
			Title string `json:"title"`
			Body  string `json:"body"`
		}

		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
			return
		}

		if strings.TrimSpace(req.Title) == "" {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": "title is required"})
			return
		}

		note, err := s.Create(strings.TrimSpace(req.Title), req.Body)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}

		writeJSON(w, http.StatusCreated, note)
	}
}

// getHandler returns a handler that fetches one note by its id.
func getHandler(s *store.Store) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		idStr := strings.TrimPrefix(r.URL.Path, "/notes/")
		id, err := strconv.ParseInt(idStr, 10, 64)
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "note not found"})
			return
		}

		note, err := s.Get(id)
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "note not found"})
			return
		}

		writeJSON(w, http.StatusOK, note)
	}
}

// updateHandler returns a handler that updates an existing note.
func updateHandler(s *store.Store) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		idStr := strings.TrimPrefix(r.URL.Path, "/notes/")
		id, err := strconv.ParseInt(idStr, 10, 64)
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "note not found"})
			return
		}

		var req struct {
			Title string `json:"title"`
			Body  string `json:"body"`
		}

		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid request body"})
			return
		}

		if strings.TrimSpace(req.Title) == "" {
			writeJSON(w, http.StatusUnprocessableEntity, map[string]string{"error": "title is required"})
			return
		}

		note, err := s.Update(id, strings.TrimSpace(req.Title), req.Body)
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "note not found"})
			return
		}

		writeJSON(w, http.StatusOK, note)
	}
}

// deleteHandler returns a handler that deletes a note by its id.
func deleteHandler(s *store.Store) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		idStr := strings.TrimPrefix(r.URL.Path, "/notes/")
		id, err := strconv.ParseInt(idStr, 10, 64)
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "note not found"})
			return
		}

		err = s.Delete(id)
		if err != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "note not found"})
			return
		}

		w.WriteHeader(http.StatusNoContent)
	}
}

// writeJSON writes a JSON response with the given status code.
func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		fmt.Printf("error encoding JSON: %v\n", err)
	}
}
