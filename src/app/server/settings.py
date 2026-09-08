from typing import Any
import os
import dotenv
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import load_settings
from app.server.auth import get_current_active_user

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

class SettingsPayload(BaseModel):
    llm_provider: str
    openai_base_url: str
    openai_api_key: str
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    model_name: str

@settings_router.get("")
async def get_settings(user: dict = Depends(get_current_active_user)) -> SettingsPayload:
    # Use load_settings to fetch the current values loaded in memory/env
    s = load_settings()
    return SettingsPayload(
        llm_provider=s.llm_provider,
        openai_base_url=s.openai_base_url,
        openai_api_key=s.openai_api_key,
        anthropic_api_key=s.anthropic_api_key,
        google_api_key=s.google_api_key,
        model_name=s.model_name
    )

@settings_router.put("")
async def update_settings(payload: SettingsPayload, user: dict = Depends(get_current_active_user)) -> SettingsPayload:
    # Write to .env
    dotenv_file = dotenv.find_dotenv()
    if not dotenv_file:
        # Create a .env if it doesn't exist
        dotenv_file = os.path.join(os.getcwd(), ".env")
        open(dotenv_file, "a").close()

    # We only set the values that were provided
    dotenv.set_key(dotenv_file, "LLM_PROVIDER", payload.llm_provider)
    dotenv.set_key(dotenv_file, "OPENAI_BASE_URL", payload.openai_base_url)
    dotenv.set_key(dotenv_file, "OPENAI_API_KEY", payload.openai_api_key)
    dotenv.set_key(dotenv_file, "OPENAI_MODEL", payload.model_name)
    
    if payload.anthropic_api_key is not None:
        dotenv.set_key(dotenv_file, "ANTHROPIC_API_KEY", payload.anthropic_api_key)
    if payload.google_api_key is not None:
        dotenv.set_key(dotenv_file, "GOOGLE_API_KEY", payload.google_api_key)

    # Reload into the current process environment so new requests see it
    dotenv.load_dotenv(dotenv_file, override=True)
    
    return await get_settings(user)
