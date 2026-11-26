require "json"
require "sinatra/base"
require_relative "lib/notes_api"

# Initialize the database schema on startup to prevent CantOpenException
NotesApi::DB.initialize_db(File.join(ENV.fetch("DATA_DIR", "data"), "notes.db"))

# The service. config.ru starts it; unit tests call it directly.
class App < Sinatra::Base
  set :host_authorization, { permitted_hosts: [] }

  helpers do
    def db_path
      File.join(ENV.fetch("DATA_DIR", "data"), "notes.db")
    end

    def reply_json(code, value = nil)
      content_type :json
      if value.nil?
        # Use status + return instead of halt so the Content-Type header
        # set above is preserved on the response object.  Rack::Test reads
        # the response object directly; halt(code) creates a new response
        # context that discards prior modifications.
        status code
        ""
      else
        halt code, JSON.generate(value)
      end
    end
  end

  get "/health" do
    reply_json 200, { "status" => "ok" }
  end

  post "/notes" do
    data = begin
      JSON.parse(request.body.read)
    rescue JSON::ParserError
      nil
    end

    if data.nil?
      return reply_json 400, { "error" => "Invalid JSON" }
    end

    # Ensure data is a Hash (JSON object), not an array or scalar
    unless data.is_a?(Hash)
      return reply_json 400, { "error" => "Invalid JSON" }
    end

    NotesApi::DB.with_db(db_path) do |conn|
      begin
        result = NotesApi::Service.create_note(conn, data)
        reply_json 201, result
      rescue ArgumentError => e
        reply_json 400, { "error" => e.message }
      rescue StandardError => e
        reply_json 500, { "error" => "Internal Server Error" }
      end
    end
  end

  get "/notes" do
    NotesApi::DB.with_db(db_path) do |conn|
      notes = NotesApi::Service.list_notes(conn)
      reply_json 200, notes
    end
  end

  get "/notes/:id" do
    id_param = params["id"]
    id = Integer(id_param, exception: false)

    if id.nil?
      return reply_json 400, { "error" => "Invalid note id" }
    end

    NotesApi::DB.with_db(db_path) do |conn|
      note = NotesApi::Service.fetch_note(conn, id)

      if note.nil?
        return reply_json 404, { "error" => "Note not found" }
      end

      reply_json 200, note
    end
  end

  put "/notes/:id" do
    id_param = params["id"]
    id = Integer(id_param, exception: false)

    if id.nil?
      return reply_json 400, { "error" => "Invalid note id" }
    end

    data = begin
      JSON.parse(request.body.read)
    rescue JSON::ParserError
      nil
    end

    if data.nil?
      return reply_json 400, { "error" => "Invalid JSON" }
    end

    # Ensure data is a Hash (JSON object), not an array or scalar
    unless data.is_a?(Hash)
      return reply_json 400, { "error" => "Invalid JSON" }
    end

    NotesApi::DB.with_db(db_path) do |conn|
      begin
        result = NotesApi::Service.update_note(conn, id, data)
        if result.nil?
          return reply_json 404, { "error" => "Note not found" }
        end
        reply_json 200, result
      rescue ArgumentError => e
        reply_json 400, { "error" => e.message }
      rescue StandardError => e
        reply_json 500, { "error" => "Internal Server Error" }
      end
    end
  end

  delete "/notes/:id" do
    id_param = params["id"]
    id = Integer(id_param, exception: false)

    if id.nil?
      return reply_json 400, { "error" => "Invalid note id" }
    end

    NotesApi::DB.with_db(db_path) do |conn|
      deleted = NotesApi::Service.delete_note(conn, id)

      if !deleted
        return reply_json 404, { "error" => "Note not found" }
      end

      reply_json 204
    end
  end
end
