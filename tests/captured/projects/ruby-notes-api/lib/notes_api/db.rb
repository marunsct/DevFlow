require "sqlite3"
require "json"
require "fileutils"

module NotesApi
  module DB
    # Opens a connection to the SQLite database at db_path.
    # Creates the 'notes' table if it does not exist.
    # Closes the connection.
    def self.initialize_db(db_path)
      FileUtils.mkdir_p(File.dirname(db_path))
      conn = SQLite3::Database.new(db_path)
      conn.execute <<-SQL
        CREATE TABLE IF NOT EXISTS notes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          body TEXT NOT NULL
        );
      SQL
      conn.close
    end

    # Opens a new SQLite connection.
    # Enables WAL mode.
    # Sets busy_timeout to 5000ms.
    # Yields the connection to the block.
    # Ensures the connection is closed after the block executes.
    # Returns the result of the block.
    def self.with_db(db_path)
      conn = SQLite3::Database.new(db_path)
      conn.results_as_hash = true
      conn.execute("PRAGMA journal_mode=WAL")
      conn.busy_timeout(5000)
      begin
        yield conn
      ensure
        conn.close
      end
    end

      # Executes INSERT INTO notes (title, body) VALUES (?, ?) with parameterized query.
      # Returns the last inserted row id.
      # Wrapped in a transaction.
      # NOTE: sqlite3 gem 2.x execute(sql, params) expects params as an array,
      # not as separate arguments.
      def self.create_note(conn, title, body)
        conn.transaction do
          conn.execute("INSERT INTO notes (title, body) VALUES (?, ?)", [title, body])
          conn.last_insert_row_id
        end
      end

    # Executes SELECT * FROM notes WHERE id = ?.
    # Returns the row as a hash or nil if not found.
    def self.fetch_note(conn, id)
      conn.execute("SELECT * FROM notes WHERE id = ?", id).first
    end

    # Executes SELECT * FROM notes ORDER BY id ASC.
    # Returns an array of hashes.
    def self.list_notes(conn)
      conn.execute("SELECT * FROM notes ORDER BY id ASC").to_a
    end

      # Executes UPDATE notes SET title = ?, body = ? WHERE id = ?.
      # Returns true if a row was updated, false otherwise.
      # Wrapped in a transaction.
      # NOTE: sqlite3 gem 2.x execute(sql, params) expects params as an array,
      # not as separate arguments.
      def self.update_note(conn, id, title, body)
        conn.transaction do
          conn.execute("UPDATE notes SET title = ?, body = ? WHERE id = ?", [title, body, id])
          conn.changes > 0
        end
      end

    # Executes DELETE FROM notes WHERE id = ?.
    # Returns true if a row was deleted, false otherwise.
    # Wrapped in a transaction.
    def self.delete_note(conn, id)
      conn.transaction do
        conn.execute("DELETE FROM notes WHERE id = ?", id)
        conn.changes > 0
      end
    end
  end
end
