"""
Minimal FastAPI application implementing the specification.
"""
import uuid
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from .auth import get_current_user
from .agent_graph import AgentExecutor

app = FastAPI(title="Test Product Intake API")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class ConversationStartResponse(BaseModel):
    conversation_id: str

class StepRequest(BaseModel):
    message: str

class StepResponse(BaseModel):
    conversation_id: str
    response: str
    state: dict

# In-memory store for conversation IDs (for demo only)
_conversations = set()

@app.post("/conversations", response_model=ConversationStartResponse)
async def start_conversation(token: str = Depends(oauth2_scheme)):
    # Authentication handled by dependency
    conv_id = str(uuid.uuid4())
    _conversations.add(conv_id)
    return ConversationStartResponse(conversation_id=conv_id)

@app.post("/conversations/{conv_id}/step", response_model=StepResponse)
async def step_conversation(
    conv_id: str,
    req: StepRequest,
    token: str = Depends(oauth2_scheme),
):
    if conv_id not in _conversations:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    # Execute agent step
    response_text, new_state = await AgentExecutor.run(conv_id, req.message)
    return StepResponse(
        conversation_id=conv_id,
        response=response_text,
        state=new_state,
    )

# Placeholder token endpoint for OAuth2 flow (not secure)
@app.post("/token")
async def login():
    # In a real app, validate credentials and return JWT
    return {"access_token": "dummy-token", "token_type": "bearer"}
