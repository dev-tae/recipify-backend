from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field, ConfigDict, model_validator

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
class RecipeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    ingredients: list[str]
    cuisine: CuisineType = "Any"
    audience: AudienceType = "Everyone"
    servings: int = 1

    # Canonical server-side field
    titles_to_avoid: list[str] = Field(default_factory=list, alias="titlesToAvoid")

    # Back-compat: some clients may send "avoidTitles"
    avoidTitles: list[str] | None = Field(default=None, alias="avoidTitles")

    @model_validator(mode="before")
    @classmethod
    def _coalesce_avoid_titles(cls, data: dict):
        if not isinstance(data, dict):
            return data
        # If client sent "avoidTitles", normalize it into "titlesToAvoid"
        if "avoidTitles" in data and "titlesToAvoid" not in data:
            data["titlesToAvoid"] = data["avoidTitles"]
        # Ensure we always have a list for downstream code
        if "titlesToAvoid" not in data or data["titlesToAvoid"] is None:
            data["titlesToAvoid"] = []
        return data

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
        body.titles_to_avoid,   # ✅ normalized list
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
        body.titles_to_avoid,   # ✅ normalized list
    )
    return EventSourceResponse(gen)
