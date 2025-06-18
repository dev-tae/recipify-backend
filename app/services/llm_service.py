from __future__ import annotations

import hashlib, json, re
from typing import Literal, Optional, List, Union

from async_lru import alru_cache
from fastapi import HTTPException, status
import google.genai as genai
from google.genai.types import GenerationConfig # Import GenerationConfig


from core.config import get_settings
from app.schemas.recipe_schemas import (  # ← NEW
    CuisineType,
    AudienceType,
    Recipe,
    RecipeError,
    GeminiRecipeResponse,
    RECIPE_SCHEMA,
)

# ─── 2. Prompt (identical wording to the FE) ──────────────────

BABY_RULES: dict[str, str] = {
    "Baby (6-8 months)": """
- **Texture:** SMOOTH PUREE, completely free of lumps. Easily spoon-fed.
- **Ingredients:** Simple combinations (1-2 ingredients are best) to monitor for allergies and aid digestion.
- **Preparation:** Steam, boil, or bake ingredients until very soft before pureeing.
""",
    "Baby (9-12 months)": """
- **Texture:** Mashed foods with some soft lumps, or small, soft, melt-in-the-mouth finger foods.
- **Ingredients:** Can introduce more combinations of ingredients. Mild herbs (e.g., parsley, dill) are okay.
- **Preparation:** Ensure finger foods are soft, grabbable, and cut into safe shapes/sizes (e.g., pea-sized or thin strips).
""",
    "Baby (12+ months)": """
- **Texture:** Soft, chopped, easily chewable, more varied. Can be similar to family meals but cut smaller and softer.
- **Flavor:** Still mild. Minimal salt if any, wider range of mild spices/herbs acceptable.
- **Preparation:** Cook soft, chop small. Vigilant about choking hazards (e.g., halve grapes).
""",
}

GENERAL_BABY_INSTRUCTIONS = """
**CRITICAL General Guidelines for ALL Baby Recipes (6-12+ months):**
- **Flavor Profile:** ABSOLUTELY NO added salt, NO added sugar, NO honey (especially under 1 year due to botulism risk). Focus on natural flavors. Avoid strong/hot spices (e.g., chili, excessive black pepper) and excessive citrus for younger babies.
- **Safety First:** ALWAYS prioritize avoiding choking hazards. Ensure foods are cooked to appropriate softness. Introduce common allergens cautiously, one at a time.
- **Forbidden Items:** NO honey (under 1 year). NO whole nuts or seeds. NO cow's milk as main drink (under 1 year; small amounts in cooking okay if appropriate). NO highly processed foods.
""".strip()


def PROMPT_TEMPLATE(
        ingredients_list: list[str],
        cuisine: str,
        audience: str,
        servings: int,
        all_titles_to_avoid: list[str] | None = None,
) -> str:
    ingredients_string = ", ".join(ingredients_list)
    assumed_staples = "salt, black pepper, water, neutral cooking oil (e.g., vegetable, canola)"

    audience_specific_instructions = BABY_RULES.get(audience, "Standard seasoning and preparation.")
    if audience.startswith("Baby"):
        audience_specific_instructions = (
                GENERAL_BABY_INSTRUCTIONS + "\n" + audience_specific_instructions
        )

    if cuisine != "Any":
        cuisine_instructions = (
            f'The desired cuisine style is **{cuisine}**. Strive to create a recipe that authentically reflects this style, using appropriate flavor profiles and techniques.'
        )
    else:
        cuisine_instructions = (
            "The user has not specified a particular cuisine. You have flexibility, but ensure the dish is coherent and appealing based on the provided ingredients."
        )

    if all_titles_to_avoid and len(all_titles_to_avoid) > 0:
        titles_to_avoid_string = '"' + "; ".join(all_titles_to_avoid) + '"'
        recipe_variety_content = (
            f"To provide variety, please try to AVOID generating recipes that are very similar to these titles: {titles_to_avoid_string}\n"
            "Guidance: Aim for a fresh culinary experience. If ingredients strongly point to one of these, or creativity is limited, you may still suggest it, but ideally, offer a different dish or a new angle. Prioritize novelty."
        )
    else:
        titles_to_avoid_string = "N/A"
        recipe_variety_content = "No specific meals to avoid were provided. Generate freely."

    avoid_titles_line = (
        f'Avoid these titles if possible: {titles_to_avoid_string}' if all_titles_to_avoid and len(
            all_titles_to_avoid) > 0 else ""
    )

    return f"""
You are "Recipify AI Chef".
Your *entire response* MUST be *ONLY* a single JSON object. No other text, explanations, or conversational fluff before, after, or inside the JSON. Adhere strictly to JSON syntax.

### Expected JSON Output Structure:
If successful:
    {{
      "title": "Recipe Title (e.g., 'Simple Chicken and Veggie Stir-fry')",
      "description": "A short, appealing description of the dish (1-2 sentences).",
      "prepTime": "e.g., '15 minutes'",
      "cookTime": "e.g., '25 minutes'",
      "servings": "e.g., '{servings} adult servings' or 'Approx. {servings} baby portions (6-8 months)'",
      "ingredientsUsed": [
        {{ "name": "Ingredient Name", "quantity": "Amount", "unit": "e.g., cups, grams, tbsp, or 'to taste' (if appropriate for audience)" }}
      ],
      "instructions": [
        "Clear, step-by-step cooking instruction.",
        "Another step..."
      ],
      "notes": "Optional: cooking tips, storage advice, simple variations using ONLY provided ingredients or assumed staples. Notes must be age-appropriate for babies/toddlers."
    }}

If a recipe cannot be generated due to constraints:
    {{
      "error": "A polite and clear message explaining why a recipe cannot be generated. E.g., 'The ingredients (e.g., only chili peppers) are not suitable for a baby food recipe.' or 'With just water and salt, I can't create a full recipe.'"
    }}

### Recipe Generation Rules:
1.  **Ingredients Source:**
    *   Primarily use a subset or all of the user-provided ingredients: "{ingredients_string}".
    *   **Assumed Staples:** You may assume the user has basic staples: **{assumed_staples}**.
    *   **CRITICAL:** If your recipe *requires* any of these assumed staples for a standard preparation, you **MUST include them in the "ingredientsUsed" list** with appropriate quantities (e.g., "1 tsp salt", "2 tbsp oil"). Do NOT introduce other ingredients.
    *   If a liquid base is needed (e.g., for a shake, soup) and not provided by user, 'Water' from assumed staples may be used if sensible, and MUST be listed in 'ingredientsUsed'.

2.  **Edibility & Sanity:** The recipe must be for an **edible dish** with **common and sensible ingredient combinations**. Avoid unsafe or bizarre pairings.

3.  **Sufficiency Check:** If provided ingredients (even with staples) are insufficient for ANY reasonable recipe (e.g., just "water"), nonsensical, or cannot form a coherent dish, respond with the error JSON.

4.  **Cuisine Style:** {cuisine_instructions}

5.  **Audience & Servings:**
    *   Target Audience: **{audience}**. Adhere to the following guidelines:
        {audience_specific_instructions}
    *   Desired Servings: Approximately **{servings} serving(s)**. Adjust ingredient quantities and "servings" field accordingly. Note: A "serving" for babies/toddlers is smaller than an adult's.

6.  **Recipe Variety:** {recipe_variety_content}

7.  **No External Text:** Absolutely NO text or characters outside the main JSON object.

---
User provided ingredients: "{ingredients_string}"
Selected cuisine: "{cuisine}"
Selected audience: "{audience}"
Desired servings: {servings}
{avoid_titles_line}
---
Respond with ONLY the JSON object.
""".strip()


# ─── 3. Gemini client with response_schema & JSON lock ───────
settings = get_settings()

# --- Configure Gemini API Key Globally (once) ---

if settings.GEMINI_API_KEY:
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        print("Gemini API Key configured successfully.")
    except Exception as e:
        print(f"ERROR: Failed to configure Gemini API Key: {e}")
        # Decide how to handle this - raise error, log, etc.
        # If key is essential, app might not be able to start/function.
else:
    print("WARNING: GEMINI_API_KEY not found in settings. Gemini features will be unavailable.")

# --- Model Initialization ---
# Initialize the model instance after genai.configure has been called.
# This can be a global instance in this module if settings don't change per request.

_gemini_model = None
if settings.GEMINI_API_KEY:
    try:
        # Create a GenerationConfig instance
        current_generation_config = GenerationConfig(
            temperature=settings.GEMINI_TEMP,
            response_mime_type="application/json",
            response_schema=RECIPE_SCHEMA,  # Pass the Pydantic model class here
        )

        _gemini_model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL_NAME,
            generation_config=current_generation_config,  # Pass the instance
            # safety_settings=... # You can also configure safety settings here if needed
        )
        print(f"Gemini model '{settings.GEMINI_MODEL_NAME}' initialized.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Gemini model '{settings.GEMINI_MODEL_NAME}': {e}")
        _gemini_model = None  # Ensure it's None if initialization fails
else:
    print("WARNING: Gemini model name or API key missing. Model not initialized.")

_fence = re.compile(r"^```(\w+)?\s*\n?(.*?)\n?```$", re.S)


# ─── 4. Tiny helper: hash prompt to stable cache key ──────────
def _hash_key(*parts) -> str:
    blob = json.dumps(parts, sort_keys=True, default=list).encode()
    return hashlib.sha256(blob).hexdigest()


# ─── 5. Async in-memory TTL cache (async-lru) ────────────────
@alru_cache(maxsize=settings.GEMINI_CACHE_MAXSIZE, ttl=settings.GEMINI_CACHE_TTL)
async def _cached_llm_call(cache_key: str, prompt: str):
    return await _gemini_model.generate_content_async(prompt)


# ─── 6. Public API: single-shot call (used by HTTP route) ────
async def generate_recipe_from_ingredients(
        ingredients: List[str],
        cuisine: CuisineType,
        audience: AudienceType,
        servings: int,
        titles_to_avoid: Optional[List[str]] = None,
) -> GeminiRecipeResponse:
    if not settings.GEMINI_API_KEY:
        raise HTTPException(500, "Gemini API key missing")

    prompt = PROMPT_TEMPLATE(ingredients, cuisine, audience, servings, titles_to_avoid)
    cache_key = _hash_key(ingredients, cuisine, audience, servings, titles_to_avoid)

    try:
        response = await _cached_llm_call(cache_key, prompt)
    except Exception as e:
        print(f"DEBUG_LLM_ERROR: Original exception from Gemini call: {type(e).__name__} - {str(e)}")  # <<< ADD THIS
        msg = str(e).lower()
        if "quota" in msg or "rate" in msg:
            raise HTTPException(429, "LLM quota exceeded")
        if "api key" in msg:
            raise HTTPException(500, "Invalid Gemini API key")
        raise HTTPException(502, f"Gemini error: {e}")

    raw = response.text.strip()
    m = _fence.match(raw)
    if m:
        raw = m.group(2).strip()

    parsed = json.loads(raw)  # guaranteed syntactically valid
    # Runtime validation -> either Recipe or RecipeError
    if "error" in parsed:
        return RecipeError(**parsed)
    return Recipe(**parsed)


# ─── 7. Streaming generator (Server-Sent Events) ─────────────
async def stream_recipe_chunks(*args, **kwargs):
    prompt = PROMPT_TEMPLATE(*args, **kwargs)
    stream = await _gemini_model.generate_content_stream_async(prompt)
    async for part in stream:
        yield {"event": "chunk", "data": part.text}
