package main

import (
	"log"
	"net/http"
	"os"

	"notes-api/store"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	dataDir := os.Getenv("DATA_DIR")
	if dataDir == "" {
		dataDir = "data/"
	}

	if err := os.MkdirAll(dataDir, 0755); err != nil {
		log.Fatal(err)
	}

	s := store.NewStore(dataDir)
	if err := s.Load(); err != nil {
		log.Printf("Warning: failed to load store: %v", err)
	}

	mux := NewRouter(s)

	addr := "127.0.0.1:" + port
	log.Printf("Listening on %s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}
