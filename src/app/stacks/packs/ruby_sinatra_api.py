"""An HTTP service in Ruby, on Sinatra."""

from __future__ import annotations

from app.stacks.packs._service import service_pack

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

PACK = service_pack(
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
    start="exec bundle exec rackup -p $PORT -o 127.0.0.1",
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
)
