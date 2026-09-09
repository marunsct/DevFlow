from pathlib import Path
from app.models import TechnologyStack
from jinja2 import Template

COMPOSE_TEMPLATE = """\
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - NODE_ENV=production
{% if db_type %}
      - DB_HOST=db
    depends_on:
      - db

{% if 'postgres' in db_type %}
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
      POSTGRES_DB: appdb
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
{% elif 'mongo' in db_type %}
  db:
    image: mongo:6
    ports:
      - "27017:27017"
    volumes:
      - mongodata:/data/db
{% elif 'mysql' in db_type %}
  db:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: password
      MYSQL_DATABASE: appdb
    ports:
      - "3306:3306"
    volumes:
      - mysqldata:/var/lib/mysql
{% elif 'redis' in db_type %}
  cache:
    image: redis:7-alpine
    ports:
      - "6379:6379"
{% endif %}
{% endif %}
"""

class ComposeGenerator:
    def __init__(self, repo_root: str, stack: TechnologyStack):
        self.repo_root = Path(repo_root)
        self.stack = stack

    def generate(self) -> None:
        """
        Generate a docker-compose.yml file for the project based on the TechnologyStack.
        """
        db_type = self.stack.database.lower() if self.stack.database else ""
        template = Template(COMPOSE_TEMPLATE)
        compose_content = template.render(db_type=db_type)
            
        with open(self.repo_root / "docker-compose.yml", "w") as f:
            f.write(compose_content)
