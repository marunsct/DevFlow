# Stage 1: Build the React Frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/langchain-ui
COPY langchain-ui/package*.json ./
RUN npm ci
COPY langchain-ui/ ./
RUN npm run build

# Stage 2: Build the Python Backend
FROM python:3.12-slim
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
RUN pip install uv

# Copy Python requirements
COPY pyproject.toml ./
COPY src/ ./src/
RUN uv pip install --system .
RUN uv pip install --system langgraph-checkpoint-sqlite aiosqlite PyJWT bcrypt uvicorn python-multipart

# Copy Built Frontend
COPY --from=frontend-builder /app/langchain-ui/dist /app/langchain-ui/dist

# Expose port
EXPOSE 8000

# Environment variables
ENV PYTHONPATH=/app/src
ENV WORKFLOW_REPO_ROOT=/app
ENV WORKFLOW_UPLOAD_DIR=/app/uploads

# Start the server
CMD ["python", "-m", "uvicorn", "app.server.api:app", "--host", "0.0.0.0", "--port", "8000"]
