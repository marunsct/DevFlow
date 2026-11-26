package app.notes_api.dto;

import jakarta.validation.constraints.NotBlank;

public class NoteRequest {

    @NotBlank(message = "Title must not be blank")
    private String title;

    private String body;

    public NoteRequest() {
    }

    public NoteRequest(String title, String body) {
        this.title = title;
        this.body = body;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getBody() {
        return body;
    }

    public void setBody(String body) {
        this.body = body;
    }
}
