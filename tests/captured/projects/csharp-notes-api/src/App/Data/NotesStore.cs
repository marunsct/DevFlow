using System.Text.Json;
using App.Models;

namespace App.Data;

public class NotesStore
{
    private readonly List<Note> _notes = new();
    private readonly string _filePath;
    private readonly object _lock = new object();

    public NotesStore()
    {
        string? dataDir = Environment.GetEnvironmentVariable("DATA_DIR");
        
        if (string.IsNullOrEmpty(dataDir))
        {
            dataDir = "data";
        }

        Directory.CreateDirectory(dataDir);
        _filePath = Path.Combine(dataDir, "notes.json");

        Load();
    }

    public List<Note> ReadAll()
    {
        lock (_lock)
        {
            return [.. _notes.OrderBy(n => n.Id)];
        }
    }

    public Note? GetById(int id)
    {
        lock (_lock)
        {
            return _notes.FirstOrDefault(n => n.Id == id);
        }
    }

    public Note Create(string title, string body)
    {
        if (string.IsNullOrWhiteSpace(title))
        {
            throw new ArgumentException("Title must not be empty");
        }

        int nextId;
        lock (_lock)
        {
            nextId = _notes.Any() ? _notes.Max(n => n.Id) + 1 : 1;
            var note = new Note { Id = nextId, Title = title, Body = body ?? "" };
            _notes.Add(note);
            Save();
        }

        return new Note { Id = nextId, Title = title, Body = body ?? "" };
    }

    public Note? Update(int id, string title, string body)
    {
        if (string.IsNullOrWhiteSpace(title))
        {
            throw new ArgumentException("Title must not be empty");
        }

        lock (_lock)
        {
            var note = _notes.FirstOrDefault(n => n.Id == id);
            if (note == null)
            {
                return null;
            }

            // Since Note is a record with init-only properties, we must replace the instance
            // rather than modifying properties in place.
            var updatedNote = new Note { Id = note.Id, Title = title, Body = body ?? "" };
            int index = _notes.IndexOf(note);
            if (index >= 0)
            {
                _notes[index] = updatedNote;
            }
            
            Save();
            
            return updatedNote;
        }
    }

    public bool Delete(int id)
    {
        lock (_lock)
        {
            var note = _notes.FirstOrDefault(n => n.Id == id);
            if (note == null)
            {
                return false;
            }

            _notes.Remove(note);
            Save();
            return true;
        }
    }

    /// <summary>Clears all notes from memory and deletes the data file. Used by tests to ensure clean state.</summary>
    public void Clear()
    {
        lock (_lock)
        {
            _notes.Clear();
        }
        if (File.Exists(_filePath))
        {
            File.Delete(_filePath);
        }
    }

    private void Load()
    {
        if (!File.Exists(_filePath))
        {
            return;
        }

        try
        {
            string json = File.ReadAllText(_filePath);
            var notes = JsonSerializer.Deserialize<List<Note>>(json, new JsonSerializerOptions 
            { 
                PropertyNameCaseInsensitive = true 
            });
            
            if (notes != null)
            {
                lock (_lock)
                {
                    _notes.Clear();
                    _notes.AddRange(notes);
                }
            }
        }
        catch
        {
            // If file is malformed, start with empty list
        }
    }

    private void Save()
    {
        string? tempPath = null;
        try
        {
            var json = JsonSerializer.Serialize(_notes, new JsonSerializerOptions 
            { 
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase 
            });
            
            tempPath = _filePath + ".tmp";
            File.WriteAllText(tempPath, json);
            File.Move(tempPath, _filePath, overwrite: true);
        }
        catch
        {
            if (tempPath != null && File.Exists(tempPath))
            {
                try { File.Delete(tempPath); } catch { }
            }
            throw;
        }
    }
}
