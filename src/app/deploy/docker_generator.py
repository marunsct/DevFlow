from pathlib import Path
from app.models import TechnologyStack
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
CMD ["npm", "start"]
{% else %}
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev
COPY . .
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
CMD ["java", "-jar", "app.jar"]
{% else %}
# Unsupported language {{ lang }} for automatic Dockerfile generation
{% endif %}
"""

class DockerGenerator:
    def __init__(self, repo_root: str, stack: TechnologyStack):
        self.repo_root = Path(repo_root)
        self.stack = stack

    def generate(self) -> None:
        """
        Generate a Dockerfile for the project based on the TechnologyStack.
        """
        lang = self.stack.language.lower()
        framework = self.stack.framework.lower() if self.stack.framework else ""
        
        template = Template(DOCKERFILE_TEMPLATE)
        dockerfile_content = template.render(lang=lang, framework=framework)

        with open(self.repo_root / "Dockerfile", "w") as f:
            f.write(dockerfile_content)
