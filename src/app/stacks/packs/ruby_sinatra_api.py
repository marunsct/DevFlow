"""An HTTP service in Ruby, on Sinatra."""

from __future__ import annotations

from app.stacks.packs._service import service_pack
from app.stacks.packs import _sandbox as sandbox

RUBY_VERSION = "3.3"

GEMFILE = """source "https://rubygems.org"

gem "sinatra", "~> 4.1"
gem "puma", "~> 6.5"
gem "rackup", "~> 2.2"

group :test do
  gem "rspec", "~> 3.13"
  gem "rack-test", "~> 2.2"
  gem "rspec_junit_formatter", "~> 0.6"
end
"""

APP = """require "json"
require "sinatra/base"

# The service. config.ru starts it; unit tests call it directly.
class App < Sinatra::Base
  set :host_authorization, { permitted_hosts: [] }

  get "/health" do
    content_type :json
    { status: "ok" }.to_json
  end
end
"""

CONFIG_RU = """require_relative "app"

run App
"""

SMOKE_UNIT = """require "json"
require "rack/test"
require_relative "../app"

RSpec.describe "the service" do
  include Rack::Test::Methods

  def app = App

  it "reports its health" do
    get "/health"
    expect(last_response.status).to eq(200)
    expect(JSON.parse(last_response.body)).to eq("status" => "ok")
  end
end
"""

GUIDE = """The service is Ruby on Sinatra: the `App` class in `app.rb` holds its routes (`get`,
`post` ...; split them into files under `lib/` it requires as it grows), and
`config.ru` runs it. Unit tests go in `spec/`, named `<name>_spec.rb`, using RSpec
with `Rack::Test::Methods` to call `App` directly. Run them with `bundle exec rspec`.
Gems are installed into `vendor/bundle`: add one to the `Gemfile` and run
`bundle install`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 9292:9292 -v {{project}}-data:/data {{project}}`.
FROM ruby:%(ruby)s-slim
ENV HOST=0.0.0.0 PORT=9292 DATA_DIR=/data BUNDLE_WITHOUT=test
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \\
    && rm -rf /var/lib/apt/lists/*
COPY Gemfile Gemfile.lock* ./
RUN bundle install
COPY . .
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 9292
CMD ["sh", "-c", "exec bundle exec rackup -p \\"$PORT\\" -o \\"$HOST\\""]
""" % {"ruby": RUBY_VERSION}

#: Errors a Sinatra service is known to raise, by a phrase of the defect, and their cause (`app.stacks.known_errors`).
#: Measured on one run: the store was kept in a helper's `@store ||= NotesStore.new`; Sinatra makes a new app object for
#: each request, so every request read the file afresh, and ten creates at once lost all but one - with only the write
#: under a lock, through a re-plan.
SINATRA_KNOWN_ERRORS = {
    "Writes made at the same moment are not each kept": (
        "Sinatra makes a new app object for each request, so a store kept in an instance variable (`@store ||= ...`) "
        "is made, and its file read, afresh for every request. Keep one store for the whole process (`set :store, "
        "...` read through `settings.store`, or a constant) and have the helper every route calls return that one store, "
        "never `NotesStore.new`; hold one `Mutex` across reading, changing and writing the notes, the new note's id "
        "taken inside it - a lock around the write alone still loses writes."
    ),
}

#: The pack's golden example (`StackPack.golden_example`), on Sinatra 4.1: one store for the process held in a setting
#: (Sinatra makes a new `App` object per request), `halt` for the 400 and 404, and an RSpec test through `Rack::Test`
#: that gives the app a store of its own with `App.set`.
GOLDEN_APP = r"""require "fileutils"
require "json"
require "sinatra/base"

# The items, kept in one JSON file under DATA_DIR; one Mutex covers each read-change-write.
class ItemStore
  def initialize(dir)
    @file = File.join(dir, "items.json")
    @lock = Mutex.new
  end

  def add(name)
    @lock.synchronize do
      items = load
      item = { "id" => (items.map { |i| i["id"] }.max || 0) + 1, "name" => name }
      FileUtils.mkdir_p(File.dirname(@file))
      File.write(@file, JSON.generate(items + [item]))
      item
    end
  end

  def find(id)
    @lock.synchronize { load.find { |item| item["id"] == id } }
  end

  private

  def load
    File.exist?(@file) ? JSON.parse(File.read(@file)) : []
  end
end

# The service. config.ru starts it; unit tests call it directly.
class App < Sinatra::Base
  set :host_authorization, { permitted_hosts: [] }
  # One store for the whole process: Sinatra makes a new App object for every request.
  set :store, ItemStore.new(ENV.fetch("DATA_DIR", "data"))

  helpers do
    def reply(code, value)
      content_type :json
      halt code, JSON.generate(value)
    end
  end

  get "/health" do
    content_type :json
    { status: "ok" }.to_json
  end

  post "/items" do
    data = begin
      JSON.parse(request.body.read)
    rescue JSON::ParserError
      nil
    end
    name = data.is_a?(Hash) ? data["name"].to_s.strip : ""
    reply 400, { error: "name is required" } if name.empty?
    reply 201, settings.store.add(name)
  end

  get "/items/:id" do
    item = settings.store.find(Integer(params["id"], exception: false))
    reply 404, { error: "item not found" } unless item
    reply 200, item
  end
end
"""

GOLDEN_SPEC = r"""require "json"
require "rack/test"
require "tmpdir"
require_relative "../app"

RSpec.describe "items" do
  include Rack::Test::Methods

  def app = App

  # Each example's service keeps its data in a folder of its own.
  around do |example|
    Dir.mktmpdir do |dir|
      App.set :store, ItemStore.new(dir)
      example.run
    end
  end

  it "stores an item and reads it back" do
    post "/items", JSON.generate(name: "first"), "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(201)
    id = JSON.parse(last_response.body)["id"]
    get "/items/#{id}"
    expect(last_response.status).to eq(200)
    expect(JSON.parse(last_response.body)["name"]).to eq("first")
  end

  it "refuses a missing name and answers 404 for an unknown id" do
    post "/items", "{}", "CONTENT_TYPE" => "application/json"
    expect(last_response.status).to eq(400)
    get "/items/99"
    expect(last_response.status).to eq(404)
  end
end
"""

PACK = service_pack(
    golden_example={"app.rb": GOLDEN_APP, "spec/items_spec.rb": GOLDEN_SPEC},
    known_errors=SINATRA_KNOWN_ERRORS,
    sandbox_image=sandbox.RUBY,
    name="ruby-sinatra-api",
    title="HTTP service in Ruby on Sinatra",
    language="ruby",
    frameworks=("sinatra", "rack"),
    files={
        "Gemfile": GEMFILE,
        "app.rb": APP,
        "config.ru": CONFIG_RU,
        "lib/.keep": "",
    },
    install=(
        ("bundle", "config", "set", "--local", "path", "vendor/bundle"),
        ("bundle", "install"),
    ),
    unit_test=(
        "bundle", "exec", "rspec", "--format", "progress",
        "--format", "RspecJunitFormatter", "--out", "test-results/unit.xml",
    ),
    unit_report="test-results/unit.xml",
    unit_dir="spec",
    unit_pattern="*_spec.rb",
    entrypoint="app.rb",
    start='exec bundle exec rackup -p $PORT -o "${HOST:-127.0.0.1}"',
    server_timeout_ms=90_000,
    smoke_unit=("spec/scaffold_smoke_spec.rb", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "Ruby",
        "framework": "Sinatra",
        "frontend_framework": "",
        "testing_framework": "RSpec with Rack::Test for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(
        "      - uses: ruby/setup-ruby@v1\n"
        "        with:\n"
        f'          ruby-version: "{RUBY_VERSION}"',
    ),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\nvendor/\nacceptance/\nspec/\ndata/\n"},
    gitignore="vendor/bundle/\n.bundle/\n",
    # `rackup` too: the start command runs it. Measured on one run: a work order rewrote the Gemfile without it, bundler
    # could not find the executable, and the product did not start until a fixer added it back.
    kept_lines=(("Gemfile", r"rspec_junit_formatter", '  gem "rspec_junit_formatter", "~> 0.6"', r"^end\s*$"),
                ("Gemfile", r"""^\s*gem\s+["']rackup["']""", 'gem "rackup", "~> 2.2"', r"^group\b")),
)
