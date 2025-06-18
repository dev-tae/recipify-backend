from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.services.llm_service import (
    generate_recipe_from_ingredients,
    stream_recipe_chunks,
    Recipe,
    RecipeError,
    CuisineType,
    AudienceType,
)
from auth.dependencies import get_current_supabase_user  # your existing dep

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

# ─── request body model ───────────────────────────────────────
from pydantic import BaseModel
class RecipeRequest(BaseModel):
    ingredients: list[str]
    cuisine: CuisineType = "Any"
    audience: AudienceType = "Everyone"
    servings: int = 1
    avoidTitles: list[str] | None = None

# ─── 1. standard endpoint (cached) ───────────────────────────
@router.post("/", response_model=Recipe, responses={400: {"model": RecipeError}})
async def create_recipe(
    body: RecipeRequest,
    _user=Depends(get_current_supabase_user),
):
    result = await generate_recipe_from_ingredients(
        body.ingredients,
        body.cuisine,
        body.audience,
        body.servings,
        body.avoidTitles,
    )
    if isinstance(result, RecipeError):
        raise HTTPException(400, result.error)
    return result

# ─── 2. streaming endpoint (SSE) ─────────────────────────────
@router.post("/stream")
async def create_recipe_stream(
    body: RecipeRequest,
    _user=Depends(get_current_supabase_user),
):
    gen = stream_recipe_chunks(
        body.ingredients,
        body.cuisine,
        body.audience,
        body.servings,
        body.avoidTitles,
    )
    return EventSourceResponse(gen)
