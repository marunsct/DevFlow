"""An HTTP service in Ruby, on Ruby on Rails in API mode."""

from __future__ import annotations

from app.stacks.packs import ruby_sinatra_api as ruby
from app.stacks.packs._service import service_pack

GEMFILE = """source "https://rubygems.org"

gem "rails", "~> 8.0.0"
gem "puma", ">= 6.0"
gem "sqlite3", ">= 2.1"

group :test do
  gem "minitest-reporters", "~> 1.7"
end
"""

APPLICATION = """require_relative "boot"

require "fileutils"
require "rails"
require "active_model/railtie"
require "active_record/railtie"
require "action_controller/railtie"
require "rails/test_unit/railtie"

Bundler.require(*Rails.groups)

# Where the database lives: DATA_DIR, which every test run starts empty.
FileUtils.mkdir_p(ENV.fetch("DATA_DIR", "data"))

module App
  class Application < Rails::Application
    config.load_defaults 8.0
    config.api_only = true
    config.eager_load = Rails.env.production?
    config.hosts.clear
    # A development value only: every deployment sets SECRET_KEY_BASE.
    config.secret_key_base = ENV.fetch("SECRET_KEY_BASE", "development-only-secret-key-base")
  end
end
"""

BOOT = """ENV["BUNDLE_GEMFILE"] ||= File.expand_path("../Gemfile", __dir__)

require "bundler/setup"
"""

ENVIRONMENT = """require_relative "application"

Rails.application.initialize!
"""

ROUTES = """Rails.application.routes.draw do
  get "health", to: "health#show"
end
"""

DATABASE = """default: &default
  adapter: sqlite3
  pool: 5
  timeout: 5000

development:
  <<: *default
  database: <%= ENV.fetch("DATA_DIR", "data") %>/development.sqlite3

test:
  <<: *default
  database: <%= ENV.fetch("DATA_DIR", "data") %>/test.sqlite3

production:
  <<: *default
  database: <%= ENV.fetch("DATA_DIR", "data") %>/production.sqlite3
"""

CONFIG_RU = """require_relative "config/environment"

run Rails.application
Rails.application.load_server
"""

RAKEFILE = """require_relative "config/application"

Rails.application.load_tasks
"""

BIN_RAILS = """#!/usr/bin/env ruby
APP_PATH = File.expand_path("../config/application", __dir__)
require_relative "../config/boot"
require "rails/commands"
"""

APPLICATION_CONTROLLER = """class ApplicationController < ActionController::API
end
"""

HEALTH = """class HealthController < ApplicationController
  def show
    render json: { status: "ok" }
  end
end
"""

TEST_HELPER = """# Kept by the harness: the unit tests report through this file.
ENV["RAILS_ENV"] ||= "test"
require_relative "../config/environment"
require "rails/test_help"
require "minitest/reporters"

Minitest::Reporters.use! [
  Minitest::Reporters::DefaultReporter.new,
  Minitest::Reporters::JUnitReporter.new("test-results/unit"),
]
"""

SMOKE_UNIT = """require "test_helper"

class ScaffoldSmokeTest < ActionDispatch::IntegrationTest
  test "the service reports its health" do
    get "/health"
    assert_response :success
    assert_equal({ "status" => "ok" }, response.parsed_body)
  end
end
"""

GUIDE = """The service is Ruby on Rails in API mode: routes in `config/routes.rb`, controllers in
`app/controllers/` (each inheriting `ApplicationController`, answering with `render
json:`), models in `app/models/`. Generate a model with `bundle exec rails generate
model <Name> <field:type ...>` and keep the migration it writes; `bundle exec rails
db:migrate` applies it. Unit tests go in `test/` - `test/models/<name>_test.rb`,
`test/integration/<area>_test.rb` (classes inheriting `ActionDispatch::IntegrationTest`,
calling `get`, `post` ...) - starting with `require "test_helper"`. Run them with
`bundle exec rails test`. Gems are installed into `vendor/bundle`: add one to the
`Gemfile` and run `bundle install`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 3000:3000 -e SECRET_KEY_BASE=... -v {{project}}-data:/data {{project}}`.
FROM ruby:%(ruby)s-slim
ENV HOST=0.0.0.0 PORT=3000 DATA_DIR=/data RAILS_ENV=production BUNDLE_WITHOUT=test
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \\
    && rm -rf /var/lib/apt/lists/*
COPY Gemfile Gemfile.lock* ./
RUN bundle install
COPY . .
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 3000
CMD ["sh", "-c", "bundle exec rails db:prepare && exec bundle exec rails server -b \\"$HOST\\" -p \\"$PORT\\""]
""" % {"ruby": ruby.RUBY_VERSION}

PACK = service_pack(
    name="ruby-rails-api",
    title="HTTP service in Ruby on Rails (API mode)",
    language="ruby",
    frameworks=("rails", "ruby on rails", "ror"),
    files={
        "Gemfile": GEMFILE,
        "Rakefile": RAKEFILE,
        "config.ru": CONFIG_RU,
        "bin/rails": BIN_RAILS,
        "config/application.rb": APPLICATION,
        "config/boot.rb": BOOT,
        "config/environment.rb": ENVIRONMENT,
        "config/routes.rb": ROUTES,
        "config/database.yml": DATABASE,
        "app/controllers/application_controller.rb": APPLICATION_CONTROLLER,
        "app/controllers/health_controller.rb": HEALTH,
        "app/models/.keep": "",
        "db/.keep": "",
        "test/test_helper.rb": TEST_HELPER,
    },
    install=ruby.PACK.install[:2],
    unit_test=("bundle", "exec", "rails", "test"),
    unit_report="test-results/unit",
    unit_dir="test",
    unit_pattern="*_test.rb",
    start="bundle exec rails db:prepare && exec bundle exec rails server -b 127.0.0.1 -p $PORT",
    server_timeout_ms=180_000,
    smoke_unit=("test/integration/scaffold_smoke_test.rb", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "Ruby",
        "framework": "Ruby on Rails",
        "frontend_framework": "",
        "testing_framework": "Minitest (rails test) for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=ruby.PACK.ci_setup[:1],
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\nvendor/\nacceptance/\ntest/\ndata/\nlog/\ntmp/\n"},
    kept_files=("test/test_helper.rb",),
    gitignore="vendor/bundle/\n.bundle/\nlog/\ntmp/\n",
)
