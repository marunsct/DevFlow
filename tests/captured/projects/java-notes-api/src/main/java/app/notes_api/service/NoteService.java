package app.notes_api.service;

import app.notes_api.exception.ResourceNotFoundException;
import app.notes_api.model.Note;
import app.notes_api.repository.NoteRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class NoteService {

    private final NoteRepository noteRepository;

    public NoteService(NoteRepository noteRepository) {
        this.noteRepository = noteRepository;
    }

    @Transactional
    public Note createNote(String title, String body) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        Note note = new Note(0, title, body);
        return noteRepository.createNote(note);
    }

    @Transactional(readOnly = true)
    public Note getById(long id) {
        Note note = noteRepository.getById(id);
        if (note == null) {
            throw new ResourceNotFoundException("Note not found");
        }
        return note;
    }

    @Transactional(readOnly = true)
    public List<Note> getAll() {
        return noteRepository.getAll();
    }

    @Transactional
    public Note updateNote(long id, String title, String body) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        Note existing = noteRepository.getById(id);
        if (existing == null) {
            throw new ResourceNotFoundException("Note not found");
        }
        Note updated = new Note(id, title, body);
        noteRepository.updateNote(updated);
        return updated;
    }

    @Transactional
    public void deleteNote(long id) {
        Note existing = noteRepository.getById(id);
        if (existing == null) {
            throw new ResourceNotFoundException("Note not found");
        }
        noteRepository.deleteNote(id);
    }
}
