package app.notes_api.controller;

import app.notes_api.dto.NoteRequest;
import app.notes_api.model.Note;
import app.notes_api.service.NoteService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/notes")
public class NoteController {

    private final NoteService noteService;

    public NoteController(NoteService noteService) {
        this.noteService = noteService;
    }

    @PostMapping
    public ResponseEntity<Note> createNote(@Validated @RequestBody NoteRequest request) {
        String title = request.getTitle();
        String body = request.getBody() != null ? request.getBody() : "";
        Note note = noteService.createNote(title, body);
        return ResponseEntity.status(HttpStatus.CREATED).body(note);
    }

    @GetMapping
    public ResponseEntity<List<Note>> listNotes() {
        List<Note> notes = noteService.getAll();
        return ResponseEntity.ok(notes);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Note> getNote(@PathVariable long id) {
        Note note = noteService.getById(id);
        return ResponseEntity.ok(note);
    }

    @PutMapping("/{id}")
    public ResponseEntity<Note> updateNote(@PathVariable long id, @Validated @RequestBody NoteRequest request) {
        String title = request.getTitle();
        String body = request.getBody() != null ? request.getBody() : "";
        Note note = noteService.updateNote(id, title, body);
        return ResponseEntity.ok(note);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteNote(@PathVariable long id) {
        noteService.deleteNote(id);
        return ResponseEntity.noContent().build();
    }
}
