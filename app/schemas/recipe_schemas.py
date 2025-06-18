# app/schemas/recipe_schemas.py
from __future__ import annotations

from typing import Literal, List, Optional, Union

from pydantic import BaseModel, Field

# ─── Domain enums ─────────────────────────────────────────────
CuisineType = Literal[
    "Any", "Italian", "Mexican", "Korean", "Dessert", "American"
]
AudienceType = Literal[
    "Everyone",
    "Baby (6-8 months)",
    "Baby (9-12 months)",
    "Baby (12+ months)",
]

# ─── Pydantic models ─────────────────────────────────────────
class Ingredient(BaseModel):
    name: str
    quantity: str
    unit: str

class Recipe(BaseModel):
    title: str
    description: str
    prepTime: str
    cookTime: str
    servings: str
    ingredientsUsed: List[Ingredient] = Field(..., alias="ingredientsUsed")
    instructions: List[str]
    notes: Optional[str] = None

class RecipeError(BaseModel):
    error: str

# ─── Typing aliases (nice for FastAPI response_model, etc.) ──
GeminiRecipeResponse = Union[Recipe, RecipeError]

# If you still want the “response_schema” constant for Gemini:
RECIPE_SCHEMA = Recipe
