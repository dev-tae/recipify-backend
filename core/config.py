# core/config.py
import os
from functools import lru_cache

from h2.settings import Settings
from supabase import create_async_client, AsyncClient
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

SUPABASE_URL_FROM_ENV = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY_FROM_ENV = os.environ.get("SUPABASE_SERVICE_KEY")
GEMINI_API_KEY_CONFIG = os.environ.get("GEMINI_API_KEY")

_supabase_backend_client: AsyncClient = None # Rename to indicate it's "private" to this module

class Settings(BaseSettings):
    GEMINI_MODEL_NAME: str = Field(default="gemini-1.5-flash-latest")
    GEMINI_TEMP: float = Field(default=0.6, gt=0.0, le=2.0)

    GEMINI_API_KEY: str = Field(..., env="GEMINI_API_KEY")
    GEMINI_CACHE_MAXSIZE: int = Field(default=128)
    GEMINI_CACHE_TTL: int = Field(default=3600) # TTL in seconds (e.g., 1 hour)
    class Config:
        case_sensitive = True

async def init_supabase():
    global _supabase_backend_client # Use the renamed global
    print("--- Attempting to initialize Supabase backend client (init_supabase) ---")
    # ... (rest of your init_supabase function is the same, just uses _supabase_backend_client)
    if not SUPABASE_URL_FROM_ENV:
        print("FATAL_CONFIG_ERROR: SUPABASE_URL not found in environment variables.")
        return
    if not SUPABASE_SERVICE_KEY_FROM_ENV:
        print("FATAL_CONFIG_ERROR: SUPABASE_SERVICE_KEY not found in environment variables.")
        return

    print(f"DEBUG_CONFIG: SUPABASE_URL_FROM_ENV = {SUPABASE_URL_FROM_ENV}")
    print(f"DEBUG_CONFIG: SUPABASE_SERVICE_KEY_FROM_ENV is set = {bool(SUPABASE_SERVICE_KEY_FROM_ENV)}")
    if SUPABASE_SERVICE_KEY_FROM_ENV:
         print(f"DEBUG_CONFIG: SUPABASE_SERVICE_KEY_FROM_ENV (first 10 chars) = {SUPABASE_SERVICE_KEY_FROM_ENV[:10]}...")

    try:
        _supabase_backend_client = await create_async_client(
            SUPABASE_URL_FROM_ENV,
            SUPABASE_SERVICE_KEY_FROM_ENV,
        )
        if _supabase_backend_client:
            print("SUCCESS_CONFIG: Supabase backend client initialized successfully.")
        else:
            print("ERROR_CONFIG: create_async_client returned None, client NOT initialized.")
    except Exception as e:
        print(f"CRITICAL_ERROR_CONFIG: Failed to create Supabase backend client during init_supabase: {e}")
        import traceback
        traceback.print_exc()
        _supabase_backend_client = None
    print("--- Finished attempting Supabase backend client initialization ---")


# Getter function to be used as a dependency
async def get_supabase_backend_client() -> AsyncClient:
    if _supabase_backend_client is None:
        # This should ideally not happen if startup event ran correctly
        # and init_supabase was successful.
        print("CRITICAL_DEPENDENCY_ERROR: get_supabase_backend_client called but _supabase_backend_client is None!")
        # Optionally, you could try to initialize it here as a fallback,
        # but it's better to ensure startup is robust.
        # await init_supabase() # Avoid re-initializing on every call unless absolutely necessary
        # if _supabase_backend_client is None: # Check again
        raise Exception("Supabase client not initialized. Application startup might have failed.")
    return _supabase_backend_client


@lru_cache
def get_settings() -> Settings:
    return Settings()