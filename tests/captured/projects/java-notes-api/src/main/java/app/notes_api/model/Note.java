package app.notes_api.model;

/**
 * Plain data class representing a Note entity.
 * Fields: id (long), title (String), body (String).
 * Immutable via final fields and no setters.
 */
public class Note {
    private final long id;
    private final String title;
    private final String body;

    public Note(long id, String title, String body) {
        this.id = id;
        this.title = title;
        this.body = body;
    }

    public long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getBody() {
        return body;
    }
}
