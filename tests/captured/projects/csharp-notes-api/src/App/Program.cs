using System.Text.Json;
using App.Data;
using App.Models;

var builder = WebApplication.CreateBuilder(args);

// Register NotesStore as a singleton service
builder.Services.AddSingleton<NotesStore>();

var app = builder.Build();

// Health check endpoint
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

// POST /notes - Create a new note
app.MapPost("/notes", async (HttpRequest req, NotesStore store) =>
{
    string? jsonBody = await new StreamReader(req.Body).ReadToEndAsync();
    
    // Handle empty body or invalid JSON gracefully to avoid unhandled exceptions before validation
    if (string.IsNullOrWhiteSpace(jsonBody))
    {
        return Results.BadRequest(new { error = "Title is required" });
    }

    JsonDocument? doc = null;
    try
    {
        doc = JsonDocument.Parse(jsonBody);
    }
    catch (JsonException)
    {
        return Results.UnprocessableEntity(new { error = "Invalid JSON" });
    }

    if (doc == null || doc.RootElement.ValueKind == JsonValueKind.Undefined)
    {
        return Results.BadRequest(new { error = "Title is required" });
    }

    // Extract Title — return early when property is missing to avoid calling GetString() on an undefined JsonElement (which throws 500)
    if (!doc.RootElement.TryGetProperty("title", out JsonElement titleElement))
    {
        return Results.BadRequest(new { error = "Title is required" });
    }

    if (titleElement.ValueKind == JsonValueKind.Null)
    {
        return Results.BadRequest(new { error = "Title is required" });
    }

    string? strTitle = titleElement.GetString();
    if (string.IsNullOrWhiteSpace(strTitle))
    {
        return Results.BadRequest(new { error = "Title must not be empty" });
    }

    string title = strTitle!;

    // Extract Body (optional, defaults to empty string)
    string body = "";
    if (doc.RootElement.TryGetProperty("body", out JsonElement bodyElement))
    {
        if (bodyElement.ValueKind == JsonValueKind.String)
        {
            body = bodyElement.GetString() ?? "";
        }
        else if (bodyElement.ValueKind != JsonValueKind.Null)
        {
             // If body is present but not a string, treat as empty or error? 
             // Spec says body is optional string. Non-string might be invalid, but spec doesn't explicitly error on non-string body.
             // Defaulting to empty string for safety if it's not a string/null, or just take the string value.
             body = ""; 
        }
    }

    try
    {
        Note note = store.Create(title, body);
        return Results.Created($"/notes/{note.Id}", note);
    }
    catch (ArgumentException ex)
    {
        // Map validation errors from store to API responses
        if (ex.Message == "Title must not be empty")
        {
            return Results.BadRequest(new { error = "Title must not be empty" });
        }
        return Results.UnprocessableEntity(new { error = ex.Message });
    }
});

// GET /notes - List all notes
app.MapGet("/notes", (NotesStore store) =>
{
    List<Note> notes = store.ReadAll();
    return Results.Ok(notes);
});

// GET /notes/{id} - Get a note by ID
app.MapGet("/notes/{id}", (string id, NotesStore store) =>
{
    if (!int.TryParse(id, out int parsedId))
    {
        return Results.NotFound();
    }
    Note? note = store.GetById(parsedId);
    if (note == null)
    {
        return Results.NotFound();
    }
    return Results.Ok(note);
});

// PUT /notes/{id} - Update a note
app.MapPut("/notes/{id}", async (string id, HttpRequest req, NotesStore store) =>
{
    if (!int.TryParse(id, out int parsedId))
    {
        return Results.NotFound();
    }

    string? jsonBody = await new StreamReader(req.Body).ReadToEndAsync();

    if (string.IsNullOrWhiteSpace(jsonBody))
    {
        return Results.BadRequest(new { error = "Title is required" });
    }

    JsonDocument? doc = null;
    try
    {
        doc = JsonDocument.Parse(jsonBody);
    }
    catch (JsonException)
    {
        return Results.UnprocessableEntity(new { error = "Invalid JSON" });
    }

    if (doc == null || doc.RootElement.ValueKind == JsonValueKind.Undefined)
    {
        return Results.BadRequest(new { error = "Title is required" });
    }

    // Extract Title — distinguish missing/null from empty/whitespace for correct error messages
    string? strTitle;
    if (!doc.RootElement.TryGetProperty("title", out JsonElement titleElement) || titleElement.ValueKind == JsonValueKind.Null)
    {
        return Results.BadRequest(new { error = "Title is required" });
    }

    strTitle = titleElement.GetString();
    if (string.IsNullOrWhiteSpace(strTitle))
    {
        return Results.BadRequest(new { error = "Title must not be empty" });
    }

    string title = strTitle!;

    // Extract Body
    string body = "";
    if (doc.RootElement.TryGetProperty("body", out JsonElement bodyElement))
    {
        if (bodyElement.ValueKind == JsonValueKind.String)
        {
            body = bodyElement.GetString() ?? "";
        }
    }

    try
    {
        Note? updatedNote = store.Update(parsedId, title, body);
        if (updatedNote == null)
        {
            return Results.NotFound();
        }
        return Results.Ok(updatedNote);
    }
    catch (ArgumentException ex)
    {
        if (ex.Message == "Title must not be empty")
        {
            return Results.BadRequest(new { error = "Title must not be empty" });
        }
        return Results.UnprocessableEntity(new { error = ex.Message });
    }
});

// DELETE /notes/{id} - Delete a note
app.MapDelete("/notes/{id}", (string id, NotesStore store) =>
{
    if (!int.TryParse(id, out int parsedId))
    {
        return Results.NotFound();
    }
    bool deleted = store.Delete(parsedId);
    if (!deleted)
    {
        return Results.NotFound();
    }
    return Results.NoContent();
});

// Configure host to bind to specific interface and port
var hostEnv = Environment.GetEnvironmentVariable("HOST") ?? "127.0.0.1";
var portEnv = Environment.GetEnvironmentVariable("PORT") ?? "5000";
app.Urls.Add($"http://{hostEnv}:{portEnv}");

app.Run();

// The entry point, visible to the unit tests' WebApplicationFactory.
public partial class Program { }
