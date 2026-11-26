package store

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// ErrNoteNotFound is returned when a note with the requested ID does not exist.
var ErrNoteNotFound = errors.New("note not found")

// Note represents a single note record.
type Note struct {
	ID    int64  `json:"id"`
	Title string `json:"title"`
	Body  string `json:"body"`
}

// StoreFile is the structure persisted to disk.
type StoreFile struct {
	Notes  []Note `json:"notes"`
	NextID int64  `json:"nextId"`
}

// Store provides thread-safe in-memory access backed by a JSON file.
type Store struct {
	mu       sync.Mutex
	notes    []Note
	nextId   int64
	dataDir  string
	filePath string
}

// NewStore creates a new Store instance.
func NewStore(dataDir string) *Store {
	return &Store{
		notes:    []Note{},
		nextId:   1,
		dataDir:  dataDir,
		filePath: filepath.Join(dataDir, "notes.json"),
	}
}

// Load reads the store from disk. If the file does not exist or is invalid, it initializes with empty state.
func (s *Store) Load() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	data, err := os.ReadFile(s.filePath)
	if err != nil {
		if os.IsNotExist(err) {
			s.notes = []Note{}
			s.nextId = 1
			return nil
		}
		// On other read errors, log warning and continue with empty state as per spec
		fmt.Printf("Warning: failed to read store file: %v\n", err)
		s.notes = []Note{}
		s.nextId = 1
		return nil
	}

	var sf StoreFile
	if err := json.Unmarshal(data, &sf); err != nil {
		fmt.Printf("Warning: failed to unmarshal store file: %v\n", err)
		s.notes = []Note{}
		s.nextId = 1
		return nil
	}

	s.notes = sf.Notes
	s.nextId = sf.NextID
	return nil
}

// Save writes the current state of the store to disk atomically.
func (s *Store) Save() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	data, err := json.MarshalIndent(StoreFile{
		Notes:  s.notes,
		NextID: s.nextId,
	}, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal notes: %w", err)
	}

	dir := filepath.Dir(s.filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("create data dir: %w", err)
	}

	tmpFile, err := os.CreateTemp(dir, "*.json")
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}
	tmpPath := tmpFile.Name()

	// Set permissions to 0644 per ADR-14 (file permissions for data file)
	if err := tmpFile.Chmod(0644); err != nil {
		tmpFile.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("chmod temp file: %w", err)
	}

	if _, err := tmpFile.Write(data); err != nil {
		tmpFile.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("write temp file: %w", err)
	}

	if err := tmpFile.Close(); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("close temp file: %w", err)
	}

	if err := os.Rename(tmpPath, s.filePath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("rename temp file: %w", err)
	}

	return nil
}

// Create adds a new note and returns it with its assigned ID.
func (s *Store) Create(title string, body string) (Note, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	id := s.nextId
	s.nextId++

	note := Note{
		ID:    id,
		Title: title,
		Body:  body,
	}
	s.notes = append(s.notes, note)

	if err := s.saveInternal(); err != nil {
		return Note{}, fmt.Errorf("save after create: %w", err)
	}

	return note, nil
}

// Get retrieves a note by its ID.
func (s *Store) Get(id int64) (Note, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, note := range s.notes {
		if note.ID == id {
			return note, nil
		}
	}
	return Note{}, ErrNoteNotFound
}

// Update modifies an existing note's title and body.
func (s *Store) Update(id int64, title string, body string) (Note, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for i, note := range s.notes {
		if note.ID == id {
			note.Title = title
			note.Body = body
			s.notes[i] = note
			if err := s.saveInternal(); err != nil {
				return Note{}, fmt.Errorf("save after update: %w", err)
			}
			return note, nil
		}
	}
	return Note{}, ErrNoteNotFound
}

// Delete removes a note by its ID.
func (s *Store) Delete(id int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	for i, note := range s.notes {
		if note.ID == id {
			s.notes = append(s.notes[:i], s.notes[i+1:]...)
			if err := s.saveInternal(); err != nil {
				return fmt.Errorf("save after delete: %w", err)
			}
			return nil
		}
	}
	return ErrNoteNotFound
}

// GetNotes returns a copy of all notes in insertion order.
func (s *Store) GetNotes() []Note {
	s.mu.Lock()
	defer s.mu.Unlock()

	notesCopy := make([]Note, len(s.notes))
	copy(notesCopy, s.notes)
	return notesCopy
}

// NextID returns the next ID that will be assigned.
func (s *Store) NextID() int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.nextId
}

// saveInternal writes the current state to disk. It assumes the lock is already held.
func (s *Store) saveInternal() error {
	data, err := json.MarshalIndent(StoreFile{
		Notes:  s.notes,
		NextID: s.nextId,
	}, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal notes: %w", err)
	}

	dir := filepath.Dir(s.filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("create data dir: %w", err)
	}

	tmpFile, err := os.CreateTemp(dir, "*.json")
	if err != nil {
		return fmt.Errorf("create temp file: %w", err)
	}
	tmpPath := tmpFile.Name()

	// Set permissions to 0644 per ADR-14 (file permissions for data file)
	if err := tmpFile.Chmod(0644); err != nil {
		tmpFile.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("chmod temp file: %w", err)
	}

	if _, err := tmpFile.Write(data); err != nil {
		tmpFile.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("write temp file: %w", err)
	}

	if err := tmpFile.Close(); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("close temp file: %w", err)
	}

	if err := os.Rename(tmpPath, s.filePath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("rename temp file: %w", err)
	}

	return nil
}
