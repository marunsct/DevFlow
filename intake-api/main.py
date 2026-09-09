import json
import logging
import os
import hmac
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

# Setup logging (Sprint 7)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

INTAKE_DIR = "docs/intake"
API_KEY_NAME = "X-API-KEY"

# Dependency for API Key Authentication (Sprint 4)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(api_key: str = Depends(api_key_header)):
    expected_key = os.getenv("INTAKE_API_KEY")
    if not expected_key:
        logger.error("INTAKE_API_KEY environment variable is not set. Rejecting request.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: API key not set",
        )
    if not api_key or not hmac.compare_digest(api_key.encode('utf-8'), expected_key.encode('utf-8')):
        logger.warning("Failed authentication attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return api_key

# Intake Schema (Sprint 2)
class IntakeSchema(BaseModel):
    id: uuid.UUID = Field(..., description="Unique UUID for the intake request")
    title: str = Field(..., description="Title of the product brief", max_length=255)
    content: str = Field(..., description="Markdown content of the product brief", max_length=500_000)
    metadata: dict[str, Any] | None = Field(default=None, description="Optional metadata")


# Startup event (Sprint 1 & 3)
@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(INTAKE_DIR, exist_ok=True)
    logger.info(f"Directory {INTAKE_DIR} created or already exists.")
    yield


app = FastAPI(
    title="Intake API",
    description="API for processing and retrieving product intake documents.",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Logging and Metrics Stub (Sprint 7)
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"Completed request: {request.method} {request.url.path} with status {response.status_code}")
        return response
    except Exception as e:
        logger.exception("Unhandled exception during request processing")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "ok"}


@app.post("/intakes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key)])
def create_intake(intake: IntakeSchema, response: Response):
    file_path = os.path.join(INTAKE_DIR, f"{str(intake.id)}.md")
    
    # Idempotency (Sprint 5)
    if os.path.exists(file_path):
        logger.info(f"Intake {str(intake.id)} already exists. Returning 200 OK.")
        response.status_code = status.HTTP_200_OK
        return {"id": str(intake.id), "message": "Intake already exists"}

    # File persistence (Sprint 3)
    try:
        with open(file_path, "w") as f:
            f.write(f"# {intake.title}\n\n{intake.content}")
        
        # Optional metadata
        if intake.metadata:
            meta_path = os.path.join(INTAKE_DIR, f"{str(intake.id)}_meta.json")
            with open(meta_path, "w") as f:
                json.dump(intake.metadata, f)
                
        logger.info(f"Successfully created intake {str(intake.id)}")
        return {"id": str(intake.id), "message": "Intake created successfully"}
    except Exception as e:
        logger.error(f"Failed to write intake {intake.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to persist intake")


@app.get("/intakes/{intake_id}", dependencies=[Depends(verify_api_key)])
def get_intake(intake_id: uuid.UUID, request: Request):
    # Content negotiation (Sprint 6)
    file_path = os.path.join(INTAKE_DIR, f"{str(intake_id)}.md")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Intake not found")
        
    with open(file_path, "r") as f:
        content = f.read()

    accept_header = request.headers.get("Accept", "")
    
    if "application/json" in accept_header:
        # Simple extraction of title from markdown
        lines = content.split("\n")
        title = lines[0].replace("# ", "") if lines and lines[0].startswith("# ") else "Untitled"
        body = "\n".join(lines[1:]).strip()
        
        meta = None
        meta_path = os.path.join(INTAKE_DIR, f"{str(intake_id)}_meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                meta = json.load(f)
                
        return {
            "id": str(intake_id),
            "title": title,
            "content": body,
            "metadata": meta
        }
    
    # Default to returning text/markdown or plain text
    return Response(content=content, media_type="text/markdown")
