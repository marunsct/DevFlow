"""A Dockerfile for the product this run built.

Every image this emits runs as a non-root user and ships a `.dockerignore`.
Both were missing, and §4.1 of `docs/harness-hardening-plan-part3.md` names
them: the generated image ran as root, which is the exact posture the harness's
own `docker-compose.yml` was written to avoid, and `COPY . .` with no ignore
file copied the host's `node_modules` and `.env` over the tree the build had
just installed.

Unsupported languages are refused rather than commented. The old template
emitted `# Unsupported language rust` into a file called `Dockerfile`, which is
a valid Dockerfile that builds nothing - a silent no-op where the stack
selector can choose eleven languages and this knows four.
"""

from pathlib import Path
from app.agents.tools_models import TechnologyStack
from jinja2 import Template

DOCKERFILE_TEMPLATE = """\
{% if lang in ('python', 'python3') %}
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install uv
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
ENV PYTHONUNBUFFERED=1
RUN useradd --system --create-home --uid 10001 app && chown -R app:app /app
USER app
CMD ["python", "main.py"]
{% elif lang in ('typescript', 'javascript', 'node') %}
{% if framework and ('react' in framework or 'next' in framework) %}
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
COPY --from=builder /app/package.json .
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
# COPY --from=builder /app/.next ./.next # For Next.js
USER node
CMD ["npm", "start"]
{% else %}
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev
COPY . .
USER node
CMD ["node", "index.js"]
{% endif %}
{% elif lang in ('go', 'golang') %}
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/main .
RUN adduser --system --uid 10001 app
USER app
CMD ["./main"]
{% elif lang in ('java', 'kotlin') %}
FROM eclipse-temurin:21-jdk-alpine AS builder
WORKDIR /app
COPY pom.xml .
COPY src ./src
RUN mvn clean package -DskipTests

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=builder /app/target/*.jar app.jar
RUN adduser --system --uid 10001 app
USER app
CMD ["java", "-jar", "app.jar"]
{% endif %}
"""

#: Never copied into an image. `COPY . .` with no ignore file puts the host's
#: `node_modules` over the one `npm ci` just installed - built for a different
#: platform, and the reason a generated image can fail on a machine the source
#: builds on. `.env` is worse: it bakes whatever the developer had into a layer.
DOCKERIGNORE = """\
.git
.gitignore
node_modules
__pycache__
*.pyc
.venv
venv
.env
.env.*
dist
build
coverage
target
.pytest_cache
.mypy_cache
Dockerfile
.dockerignore
"""

#: Languages this can write a Dockerfile for. The stack selector can choose
#: more, and a language absent here is refused by name rather than written out
#: as a comment - see `UnsupportedLanguage`.
SUPPORTED_LANGUAGES = frozenset({
    "python", "python3",
    "typescript", "javascript", "node",
    "go", "golang",
    "java", "kotlin",
})


class UnsupportedLanguage(ValueError):
    """No Dockerfile template exists for this stack's language."""


class DockerGenerator:
    def __init__(self, repo_root: str, stack: TechnologyStack):
        self.repo_root = Path(repo_root)
        self.stack = stack

    def generate(self) -> None:
        """Write a `Dockerfile` and a `.dockerignore`, or refuse.

        Refusing is the point of the change. The old template fell through to
        `# Unsupported language {{ lang }}`, which is a Dockerfile that builds
        nothing and reports success - and the stack selector can choose rust,
        csharp, ruby, php, swift, dart and elixir, none of which it knew.
        """
        lang = (self.stack.language or "").lower()
        framework = self.stack.framework.lower() if self.stack.framework else ""

        if lang not in SUPPORTED_LANGUAGES:
            raise UnsupportedLanguage(
                f"No Dockerfile template for {lang or 'an unnamed language'}. "
                f"Templates exist for: {', '.join(sorted(SUPPORTED_LANGUAGES))}. "
                "Write one by hand, or add a template rather than shipping an "
                "image that builds nothing."
            )

        template = Template(DOCKERFILE_TEMPLATE)
        dockerfile_content = template.render(lang=lang, framework=framework)

        (self.repo_root / "Dockerfile").write_text(dockerfile_content, encoding="utf-8")
        # Beside the Dockerfile, never instead of it: a `COPY . .` without this
        # is the defect, and an image is only as good as what it did not copy.
        (self.repo_root / ".dockerignore").write_text(DOCKERIGNORE, encoding="utf-8")
