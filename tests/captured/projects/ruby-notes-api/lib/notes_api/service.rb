require_relative "db"

module NotesApi
  module Service
    # Validates that data['title'] is present and non-empty.
    # Calls DB.create_note(conn, data['title'], data['body']).
    # Returns the created note hash including the new id.
    def self.create_note(conn, data)
      title = data["title"]
      body = data["body"]

      # Validate title is present and non-empty (including whitespace-only)
      if title.nil? || title.to_s.strip.empty?
        raise ArgumentError, "Title is required"
      end

      id = DB.create_note(conn, title.to_s, body.to_s)
      
      # Fetch the created note to return the full hash with id
      DB.fetch_note(conn, id)
    end

    # Calls DB.fetch_note(conn, id).
    # Returns the note hash or nil.
    def self.fetch_note(conn, id)
      DB.fetch_note(conn, id)
    end

    # Calls DB.list_notes(conn).
    # Returns the array of note hashes.
    def self.list_notes(conn)
      DB.list_notes(conn)
    end

    # Validates that data['title'] is present and non-empty.
    # Calls DB.update_note(conn, id, data['title'], data['body']).
    # If updated, calls DB.fetch_note(conn, id) and returns the updated note hash.
    # If not updated (id not found), returns nil.
    def self.update_note(conn, id, data)
      title = data["title"]
      body = data["body"]

      # Validate title is present and non-empty (including whitespace-only)
      if title.nil? || title.to_s.strip.empty?
        raise ArgumentError, "Title is required"
      end

      updated = DB.update_note(conn, id, title.to_s, body.to_s)
      
      if updated
        DB.fetch_note(conn, id)
      else
        nil
      end
    end

    # Calls DB.delete_note(conn, id).
    # Returns the boolean result.
    def self.delete_note(conn, id)
      DB.delete_note(conn, id)
    end
  end
end
