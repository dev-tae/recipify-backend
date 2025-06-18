# auth/dependencies.py
import os
import httpx # <--- Import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials # <--- Changed to HTTPBearer
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

# It's good practice to load .env as early as possible, typically in main.py.
# However, if this module might be imported before main.py fully initializes env vars for some reason,
# this call can be a fallback. Ensure main.py's load_dotenv() is the primary one.
load_dotenv() # Can be commented out if main.py definitely handles it first

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# This check is crucial. If these are not set, nothing will work.
if not SUPABASE_URL:
    print("FATAL ERROR: SUPABASE_URL not found in environment variables.")
    # raise ValueError("SUPABASE_URL must be set in .env")
if not SUPABASE_ANON_KEY:
    print("FATAL ERROR: SUPABASE_ANON_KEY not found in environment variables.")
    # raise ValueError("SUPABASE_ANON_KEY must be set in .env")

# Use HTTPBearer for simpler bearer token handling
http_bearer_scheme = HTTPBearer()

class CurrentSupabaseUser(BaseModel):
    id: str
    email: Optional[str] = None
    # Add other fields from Supabase token if needed

async def get_current_supabase_user(
    auth_creds: HTTPAuthorizationCredentials = Depends(http_bearer_scheme)
) -> CurrentSupabaseUser:
    token = auth_creds.credentials

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print(f"ERROR in get_current_supabase_user: Supabase config missing! URL: {SUPABASE_URL}, Key present: {bool(SUPABASE_ANON_KEY)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, # Service Unavailable, as it's a server config issue
            detail="Server configuration error for Supabase URL/Key. Please contact support."
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    request_url = f"{SUPABASE_URL}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": SUPABASE_ANON_KEY
    }

    # ---- START DEBUG PRINTS ----
    print("-" * 50)
    print(f"DEBUG: Attempting to validate token with Supabase (via backend).")
    print(f"DEBUG: Request URL to Supabase: {request_url}")
    # To avoid logging the full key, let's log its presence and a snippet
    print(f"DEBUG: SUPABASE_URL from env: {SUPABASE_URL}")
    print(f"DEBUG: SUPABASE_ANON_KEY from env (is set): {bool(SUPABASE_ANON_KEY)}")
    if SUPABASE_ANON_KEY:
        print(f"DEBUG: SUPABASE_ANON_KEY (first 10 chars): {SUPABASE_ANON_KEY[:10]}...")
    print(f"DEBUG: Authorization Header sent to Supabase (token first 10 chars): Bearer {token[:10]}...")
    print(f"DEBUG: apikey Header sent to Supabase (first 10 chars): {SUPABASE_ANON_KEY[:10] if SUPABASE_ANON_KEY else 'NOT SET'}...")
    # ---- END DEBUG PRINTS ----

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(request_url, headers=headers)

            # ---- START DEBUG RESPONSE PRINTS ----
            print(f"DEBUG: Supabase Response Status Code: {response.status_code}")
            # It's good to see the text for errors, json() might fail if not JSON
            print(f"DEBUG: Supabase Response Text: {response.text}")
            # ---- END DEBUG RESPONSE PRINTS ----

            response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
            user_data = response.json()

            if not user_data.get("id"):
                print("ERROR: 'id' field missing from Supabase user data.")
                raise credentials_exception

            return CurrentSupabaseUser(id=user_data["id"], email=user_data.get("email"))

        except httpx.HTTPStatusError as e: # More specific exception for HTTP errors from httpx
            # This error (e.g., 401 from Supabase) is crucial.
            print(f"ERROR: HTTPStatusError calling Supabase /auth/v1/user: {e}. Response: {e.response.text}")
            # If Supabase itself returns 401, it means the token or anon_key was bad *for Supabase*
            if e.response.status_code == 401:
                 # Pass Supabase's error message if available and helpful, otherwise generic
                detail_message = "Invalid token or apikey for Supabase authentication."
                try:
                    supa_error = e.response.json()
                    if "error_description" in supa_error:
                        detail_message = f"Supabase auth error: {supa_error.get('error_description', supa_error.get('msg', 'Unauthorized'))}"
                    elif "msg" in supa_error:
                         detail_message = f"Supabase auth error: {supa_error.get('msg', 'Unauthorized')}"
                except:
                    pass # Keep default detail_message
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=detail_message,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Authentication service error: Supabase status {e.response.status_code}"
            )
        except httpx.RequestError as e:
            print(f"ERROR: HTTPX RequestError connecting to Supabase: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Error connecting to authentication service: {str(e)}"
            )
        except Exception as e:
            print(f"ERROR: Unexpected error during Supabase token validation: {type(e).__name__} - {e}")
            raise credentials_exception