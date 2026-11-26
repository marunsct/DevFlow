require "json"
require "rack/test"
require "tmpdir"
require_relative "../app"

RSpec.describe "Notes API" do
  include Rack::Test::Methods

  def app
    App
  end

  around do |example|
    Dir.mktmpdir do |dir|
      ENV["DATA_DIR"] = dir
      # Initialize the database for this test's isolated directory
      NotesApi::DB.initialize_db(File.join(dir, "notes.db"))
      example.run
    end
  end

  # AC-1: POST /notes -> 201
  it "creates a note and returns 201 with the note" do
    post "/notes", JSON.generate(title: "Meeting Notes", body: "Discuss project timeline"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(201)
    note = JSON.parse(last_response.body)
    expect(note).to have_key("id")
    expect(note).to have_key("title")
    expect(note).to have_key("body")
    expect(note["title"]).to eq("Meeting Notes")
    expect(note["body"]).to eq("Discuss project timeline")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-2: GET /notes -> 200
  it "lists all notes ordered by id ASC" do
    post "/notes", JSON.generate(title: "First", body: "Body 1"), "CONTENT_TYPE" => "application/json"
    post "/notes", JSON.generate(title: "Second", body: "Body 2"), "CONTENT_TYPE" => "application/json"

    get "/notes"
    expect(last_response.status).to eq(200)
    notes = JSON.parse(last_response.body)
    expect(notes).to be_an(Array)
    expect(notes.length).to eq(2)
    expect(notes[0]["title"]).to eq("First")
    expect(notes[1]["title"]).to eq("Second")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-3: GET /notes/{id} -> 200
  it "fetches a note by id and returns 200" do
    post "/notes", JSON.generate(title: "Single", body: "Body"), "CONTENT_TYPE" => "application/json"
    note_id = JSON.parse(last_response.body)["id"]

    get "/notes/#{note_id}"
    expect(last_response.status).to eq(200)
    note = JSON.parse(last_response.body)
    expect(note["id"]).to eq(note_id)
    expect(note["title"]).to eq("Single")
    expect(note["body"]).to eq("Body")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-4: PUT /notes/{id} -> 200
  it "updates a note and returns 200 with the updated note" do
    post "/notes", JSON.generate(title: "Old Title", body: "Old Body"), "CONTENT_TYPE" => "application/json"
    note_id = JSON.parse(last_response.body)["id"]

    put "/notes/#{note_id}", JSON.generate(title: "New Title", body: "New Body"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(200)
    note = JSON.parse(last_response.body)
    expect(note["title"]).to eq("New Title")
    expect(note["body"]).to eq("New Body")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-5: DELETE /notes/{id} -> 204
  it "deletes a note and returns 204 with empty body" do
    post "/notes", JSON.generate(title: "Delete Me", body: "Body"), "CONTENT_TYPE" => "application/json"
    note_id = JSON.parse(last_response.body)["id"]

    delete "/notes/#{note_id}"
    expect(last_response.status).to eq(204)
    expect(last_response.body).to be_empty
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-6: GET /health -> 200
  it "returns 200 with status ok" do
    get "/health"
    expect(last_response.status).to eq(200)
    body = JSON.parse(last_response.body)
    expect(body).to eq({"status" => "ok"})
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-7, AC-15: POST /notes invalid title -> 400
  it "returns 400 with error message for missing title" do
    post "/notes", JSON.generate(body: "Body without title"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Title is required")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  it "returns 400 with error message for empty title" do
    post "/notes", JSON.generate(title: "", body: "Body"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Title is required")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  it "returns 400 with error message for whitespace-only title" do
    post "/notes", JSON.generate(title: "   ", body: "Body"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Title is required")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-8: POST /notes invalid JSON -> 400
  it "returns 400 with error message for invalid JSON" do
    post "/notes", "not json", "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Invalid JSON")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-9: GET /notes/{id} not found -> 404
  it "returns 404 for non-existent note id" do
    get "/notes/999"
    expect(last_response.status).to eq(404)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Note not found")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-10: PUT /notes/{id} not found -> 404
  it "returns 404 for updating non-existent note id" do
    put "/notes/999", JSON.generate(title: "Title", body: "Body"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(404)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Note not found")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-11: DELETE /notes/{id} not found -> 404
  it "returns 404 for deleting non-existent note id" do
    delete "/notes/999"
    expect(last_response.status).to eq(404)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Note not found")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-12: GET /notes/{id} non-integer id -> 400
  it "returns 400 for non-integer note id" do
    get "/notes/abc"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Invalid note id")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-13: PUT /notes/{id} invalid title -> 400
  it "returns 400 for updating with missing title" do
    post "/notes", JSON.generate(title: "Title", body: "Body"), "CONTENT_TYPE" => "application/json"
    note_id = JSON.parse(last_response.body)["id"]

    put "/notes/#{note_id}", JSON.generate(body: "New Body"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Title is required")
    expect(last_response.headers["Content-Type"]).to include("application/json")

    # Verify note was not updated
    get "/notes/#{note_id}"
    expect(last_response.status).to eq(200)
    original_note = JSON.parse(last_response.body)
    expect(original_note["body"]).to eq("Body")
  end

  it "returns 400 for updating with empty title" do
    post "/notes", JSON.generate(title: "Title", body: "Body"), "CONTENT_TYPE" => "application/json"
    note_id = JSON.parse(last_response.body)["id"]

    put "/notes/#{note_id}", JSON.generate(title: "", body: "New Body"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Title is required")
    expect(last_response.headers["Content-Type"]).to include("application/json")

    # Verify note was not updated
    get "/notes/#{note_id}"
    expect(last_response.status).to eq(200)
    original_note = JSON.parse(last_response.body)
    expect(original_note["title"]).to eq("Title")
  end

  # AC-14: PUT /notes/{id} invalid JSON -> 400
  it "returns 400 for updating with invalid JSON" do
    post "/notes", JSON.generate(title: "Title", body: "Body"), "CONTENT_TYPE" => "application/json"
    note_id = JSON.parse(last_response.body)["id"]

    put "/notes/#{note_id}", "bad json", "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    body = JSON.parse(last_response.body)
    expect(body["error"]).to eq("Invalid JSON")
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-16: Content-Type header on all responses
  it "includes Content-Type: application/json on all responses" do
    # Success
    post "/notes", JSON.generate(title: "T", body: "B"), "CONTENT_TYPE" => "application/json"
    expect(last_response.headers["Content-Type"]).to include("application/json")

    get "/notes"
    expect(last_response.headers["Content-Type"]).to include("application/json")

    # Error
    get "/notes/abc"
    expect(last_response.headers["Content-Type"]).to include("application/json")

    # Not Found
    get "/notes/999"
    expect(last_response.headers["Content-Type"]).to include("application/json")
    
    # Health
    get "/health"
    expect(last_response.headers["Content-Type"]).to include("application/json")
  end

  # AC-18: Invalid input is refused without storing anything
  it "does not store note on validation error" do
    post "/notes", JSON.generate(title: "", body: "Body"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)

    get "/notes"
    expect(JSON.parse(last_response.body)).to be_empty
  end
end
