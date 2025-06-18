# routers/user_router.py
from typing import Optional
import traceback

from fastapi import APIRouter, Depends, HTTPException, status # Added status for HTTP_404_NOT_FOUND
from pydantic import BaseModel, Field # Import BaseModel and Field

# Import from auth.dependencies
from auth.dependencies import get_current_supabase_user, CurrentSupabaseUser
# Import the backend client
# For type hinting the async client (optional but good)
from core.config import get_supabase_backend_client
from supabase import AsyncClient as SupabaseAsyncClient
import core.config

# --- Pydantic Model for your public.users table data ---
class UserInDB(BaseModel):
    id: str
    avatar_url: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    is_paid_status: bool = Field(default=False) # Ensure this matches your DB column name for simplicity
                                                # If DB is 'is_paid', use alias="is_paid"

    class Config:
        orm_mode = True # Useful if you ever load data from an ORM object
        # If your DB column is 'is_paid' but Pydantic field is 'is_paid_status', use:
        # populate_by_name = True
        # And in the field: is_paid_status: bool = Field(default=False, alias="is_paid")


async def fetch_user_profile_from_db(user_id: str, client: SupabaseAsyncClient) -> Optional[UserInDB]: # Return type is UserInDB
    client: Optional[SupabaseAsyncClient] = client# Correct type hint
    print("DEBUGGING CHECKING: ", client)
    if not client:
        print(f"DB_FETCH_ERROR: Supabase backend client is not initialized (user_id: {user_id})")
        # This should ideally be a 503 Service Unavailable if the client isn't ready
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database client not available")

    try:
        print(f"DB_FETCH: Attempting to fetch profile for user_id: {user_id} from 'users' table.")
        query = client.table("users") \
            .select("id, avatar_url, email, name, is_paid_status") \
            .eq("id", user_id) \
            .maybe_single()

        print(f"DB_FETCH: About to execute query for user_id: {user_id}")
        response_object = await query.execute()
        print(response_object.raise_when_api_error)
        # print(f"DB_FETCH: Query executed for user_id {user_id}. Status: {response_object.raise_when_api_error}, Data: {response_object.data}, Error: {response_object.error_message }")

        try:
            response_object.raise_when_api_error  # will raise if error occurred
        except Exception as e:
            print(f"DB_FETCH_ERROR: Supabase/PostgREST error for user_id {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database API error: {str(e)}"
            )

        # No exception = success
        result = response_object.data
        print(f"DB_FETCH: Query executed for user_id {user_id}. Data: {result}")

        if response_object.data is not None and isinstance(response_object.data, dict):
            print(f"DB_FETCH: Profile data found for user_id {user_id}: {response_object.data}")
            try:
                # Ensure your UserInDB Pydantic model fields match the keys in response_object.data
                return UserInDB(**response_object.data)
            except Exception as pydantic_error:
                print(f"DB_FETCH_PYDANTIC_ERROR: Could not create UserInDB model from data for user {user_id}: {pydantic_error}")
                print(f"DB_FETCH_PYDANTIC_ERROR_DATA: {response_object.data}")
                # This is an internal server error because the data from DB doesn't match the expected model
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing user profile data.")
        else:
            print(f"DB_FETCH: No profile data found in 'users' table for user_id {user_id} (maybe_single returned no data or non-dict data).")
            return None

    except TypeError as te:
        print(f"DB_FETCH_TYPE_ERROR: Occurred during Supabase query for {user_id}: {te}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error during database operation (TypeError).")
    except HTTPException: # Re-raise HTTPExceptions explicitly
        raise
    except Exception as e:
        print(f"DB_FETCH_UNEXPECTED_EXCEPTION: An unexpected error occurred fetching profile for {user_id}: {type(e).__name__} - {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while fetching user profile.")


router = APIRouter(
    prefix="/api/users",
    tags=["users"],
)

@router.get("/me", response_model=UserInDB)
async def read_users_me(current_supabase_user: CurrentSupabaseUser = Depends(get_current_supabase_user), supa: SupabaseAsyncClient = Depends(get_supabase_backend_client)):
    print(f"API_LOG: /api/users/me route called for Supabase user ID: {current_supabase_user.id}, Email: {current_supabase_user.email}")

    user_profile = await fetch_user_profile_from_db(current_supabase_user.id, supa)

    if not user_profile:
        print(f"API_LOG: User profile not found by fetch_user_profile_from_db for ID: {current_supabase_user.id}. Returning 404.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # Use status from fastapi
            detail="User application profile not found in the database."
        )

    print(f"API_LOG: Successfully fetched profile for user ID: {current_supabase_user.id}. Returning profile.")
    return user_profile