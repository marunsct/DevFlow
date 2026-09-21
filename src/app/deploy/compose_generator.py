"""A compose file for the product this run built.

Credentials come from the environment and the file refuses to start without
them, which is what the harness's own `docker-compose.yml` does. §4.1 of
`docs/harness-hardening-plan-part3.md`: this generator shipped
`POSTGRES_PASSWORD: password` into every compose file it wrote, so a product
built here arrived with a plaintext default credential its own builder would
have refused to run with.

`${VAR:?message}` rather than `${VAR:-default}` deliberately. A default is how
the credential got there; a compose file that stops and names the variable is
the only version an operator cannot accidentally deploy.
"""

from pathlib import Path
from app.agents.tools_models import TechnologyStack
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
      POSTGRES_USER: ${POSTGRES_USER:?set POSTGRES_USER in .env}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: ${POSTGRES_DB:-appdb}
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
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD in .env}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-appdb}
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
