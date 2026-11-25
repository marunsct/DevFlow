using Microsoft.Data.Sqlite;

namespace App;

/// <summary>Database table name used by every method.</summary>
static class Schema
{
    /// <summary>Creates the notes table if it does not yet exist. Safe to call repeatedly.</summary>
    public static void EnsureTable(SqliteConnection conn)
    {
        using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT
            );
            """;
        cmd.ExecuteNonQuery();
    }
}

public class SQLiteRepository
{
    private readonly string _connectionString;

    public SQLiteRepository(string connectionString)
    {
        _connectionString = connectionString;
    }

    /// <summary>Opens a connection, applies WAL/busy settings, and ensures the table exists.</summary>
    private SqliteConnection Open()
    {
        var conn = new SqliteConnection(_connectionString);
        conn.Open();
        using (var pragmaCmd = conn.CreateCommand())
        {
            pragmaCmd.CommandText = "PRAGMA journal_mode=WAL;";
            pragmaCmd.ExecuteNonQuery();

            pragmaCmd.CommandText = "PRAGMA busy_timeout=5000;";
            pragmaCmd.ExecuteNonQuery();
        }
        Schema.EnsureTable(conn);
        return conn;
    }

    public async Task<NoteDto> InsertNote(NoteDto note)
    {
        using var connection = Open();

        using var transaction = connection.BeginTransaction();
        try
        {
            using (var command = connection.CreateCommand())
            {
                // Executes INSERT INTO notes (title, body) VALUES (@title, @body) RETURNING id
                command.CommandText = "INSERT INTO notes (title, body) VALUES (@title, @body) RETURNING id;";
                command.Parameters.AddWithValue("@title", note.Title);
                command.Parameters.AddWithValue("@body", note.Body is null ? (object)DBNull.Value : note.Body);

                var result = await command.ExecuteScalarAsync();

                if (result == null || result == DBNull.Value)
                {
                    throw new Exception("Failed to insert note");
                }

                note.Id = Convert.ToInt32(result);
            }

            transaction.Commit();
            return note;
        }
        catch
        {
            transaction.Rollback();
            throw;
        }
    }

    public async Task<List<NoteDto>> GetAllNotes()
    {
        using var connection = Open();

        var notes = new List<NoteDto>();
        using (var command = connection.CreateCommand())
        {
            // Executes SELECT id, title, body FROM notes
            command.CommandText = "SELECT id, title, body FROM notes;";

            using (var reader = await command.ExecuteReaderAsync())
            {
                while (await reader.ReadAsync())
                {
                    var note = new NoteDto
                    {
                        Id = reader.GetInt32(0),
                        Title = reader.GetString(1),
                        Body = reader.IsDBNull(2) ? string.Empty : reader.GetString(2)
                    };
                    notes.Add(note);
                }
            }
        }

        return notes;
    }

    public async Task<NoteDto?> GetNoteById(int id)
    {
        using var connection = Open();

        using (var command = connection.CreateCommand())
        {
            // Executes SELECT id, title, body FROM notes WHERE id = @id
            command.CommandText = "SELECT id, title, body FROM notes WHERE id = @id;";
            command.Parameters.AddWithValue("@id", id);

            using (var reader = await command.ExecuteReaderAsync())
            {
                if (await reader.ReadAsync())
                {
                    return new NoteDto
                    {
                        Id = reader.GetInt32(0),
                        Title = reader.GetString(1),
                        Body = reader.IsDBNull(2) ? string.Empty : reader.GetString(2)
                    };
                }
            }
        }

        return null;
    }

    public async Task<bool> UpdateNote(int id, NoteDto note)
    {
        using var connection = Open();

        using var transaction = connection.BeginTransaction();
        try
        {
            using (var command = connection.CreateCommand())
            {
                // Executes UPDATE notes SET title = @title, body = @body WHERE id = @id
                command.CommandText = "UPDATE notes SET title = @title, body = @body WHERE id = @id;";
                command.Parameters.AddWithValue("@title", note.Title);
                command.Parameters.AddWithValue("@body", note.Body is null ? (object)DBNull.Value : note.Body);
                command.Parameters.AddWithValue("@id", id);

                var affected = await command.ExecuteNonQueryAsync();

                if (affected > 0)
                {
                    transaction.Commit();
                    return true;
                }
            }

            transaction.Rollback();
            return false;
        }
        catch
        {
            transaction.Rollback();
            throw;
        }
    }

    public async Task<bool> DeleteNote(int id)
    {
        using var connection = Open();

        using var transaction = connection.BeginTransaction();
        try
        {
            using (var command = connection.CreateCommand())
            {
                // Executes DELETE FROM notes WHERE id = @id
                command.CommandText = "DELETE FROM notes WHERE id = @id;";
                command.Parameters.AddWithValue("@id", id);

                var affected = await command.ExecuteNonQueryAsync();

                if (affected > 0)
                {
                    transaction.Commit();
                    return true;
                }
            }

            transaction.Rollback();
            return false;
        }
        catch
        {
            transaction.Rollback();
            throw;
        }
    }
}
