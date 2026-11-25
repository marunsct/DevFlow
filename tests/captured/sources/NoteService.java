package app.notes_api;

import org.springframework.stereotype.Service;

import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;

@Service
public class NoteService {

    private final NoteRepository repository;

    public NoteService(NoteRepository repository) {
        this.repository = repository;
    }

    public NoteEntity createNote(String title, String body) {
        validateTitle(title);

        String normalizedBody = (body == null) ? "" : body;

        NoteEntity entity = new NoteEntity(null, title, normalizedBody);
        return repository.save(entity);
    }

    public List<NoteEntity> listNotes() {
        // Call findAll with Sort.by("id") to match what unit tests expect via Mockito stubs.
        return repository.findAll(org.springframework.data.domain.Sort.by("id"));
    }

    public Optional<NoteEntity> getNoteById(Integer id) {
        return repository.findById(id);
    }

    public NoteEntity updateNote(Integer id, String title, String body) {
        validateTitle(title);

        NoteEntity existing = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(id));

        String normalizedBody = (body == null) ? "" : body;
        existing.setTitle(title);
        existing.setBody(normalizedBody);

        return repository.save(existing);
    }

    public NoteEntity deleteNote(Integer id) {
        NoteEntity existing = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException(id));
        repository.deleteById(id);
        return existing;
    }

    private void validateTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Title must not be empty");
        }
    }
}
