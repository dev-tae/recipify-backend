from __future__ import annotations

import asyncio
import hashlib, json, re
import traceback
import math
import re
from typing import Iterable
from typing import Literal, Optional, List, Union

from async_lru import alru_cache
from fastapi import HTTPException, status
from google import genai                               # ✅ new SDK entrypoint
from google.genai import errors as genai_errors        # ✅ error classes
from google.genai import types                         # ✅ GenerateContentConfig, etc.

from core.config import get_settings
from app.schemas.recipe_schemas import (  # ← NEW
    CuisineType,
    AudienceType,
    Recipe,
    RecipeError,
    GeminiRecipeResponse,
    RECIPE_SCHEMA,
)

_WORD = re.compile(r"[a-z0-9]+")
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

def _normalize_title(t: str) -> list[str]:
    tokens = _WORD.findall(t.lower())
    # Optionally drop common stopwords to make matching stricter
    stop = {"the","a","an","of","for","and","with","to","on","in","easy","simple","quick"}
    return [w for w in tokens if w not in stop]

def _token_jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def _too_similar(candidate: str, avoid: list[str], threshold: float = 0.6) -> tuple[bool, str, float]:
    cand = _normalize_title(candidate)
    best_score, best_title = 0.0, ""
    for t in avoid:
        score = _token_jaccard(cand, _normalize_title(t))
        if score > best_score:
            best_score, best_title = score, t
    return (best_score >= threshold, best_title, best_score)

def _norm_words(s: str) -> list[str]:
    stop = {"the","a","an","of","for","and","with","to","on","in","easy","simple","quick","creamy","savory","crispy"}
    return [w for w in _WORD.findall(s.lower()) if w not in stop]

def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)

def _trigrams(s: str) -> dict[str, int]:
    t = s.lower().replace(" ", "_")
    return { t[i:i+3]: t.count(t[i:i+3]) for i in range(max(0, len(t)-2)) }

def _cosine(a: dict[str,int], b: dict[str,int]) -> float:
    if not a or not b: return 0.0
    dot = sum(a.get(k,0)*b.get(k,0) for k in set(a)|set(b))
    na = math.sqrt(sum(v*v for v in a.values()))
    nb = math.sqrt(sum(v*v for v in b.values()))
    return dot/(na*nb) if na and nb else 0.0

def _levenshtein(a: str, b: str) -> float:
    # returns similarity in [0,1]
    if a == b: return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0: return 0.0
    dp = list(range(lb+1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            prev, dp[j] = dp[j], min(
                dp[j]+1,
                dp[j-1]+1,
                prev + (ca != cb)
            )
    dist = dp[lb]
    return 1.0 - dist / max(la, lb)

_TECH_BUCKETS = {
    "skillet": {"skillet","pan-seared","pan","stir-fry","stirfry","sauté","saute","sear"},
    "grill": {"grill","grilled","skewer","broil","broiler"},
    "bake": {"bake","baked","roast","roasted","sheet-pan","sheetpan"},
    "mash": {"mash","puree","purée","whip"},
    "salad": {"salad","bowl","cold"},
    "soup": {"soup","stew","braise"},
    "wrap": {"wrap","taco","sandwich","pita"},
}

def _tech_labels(title: str) -> set[str]:
    words = set(_norm_words(title))
    labels = set()
    for label, keys in _TECH_BUCKETS.items():
        if words & keys:
            labels.add(label)
    return labels or {"unspecified"}

def title_similarity(a: str, b: str) -> float:
    # blend of three views; weight character & token overlap more
    wa, wb = set(_norm_words(a)), set(_norm_words(b))
    j = _jaccard(wa, wb)
    c = _cosine(_trigrams(a), _trigrams(b))
    l = _levenshtein(a.lower(), b.lower())
    return 0.45*c + 0.45*j + 0.10*l  # weighted score in [0,1]

def too_similar(candidate: str, avoid: list[str], thresh: float = 0.62) -> tuple[bool,str,float]:
    best, hit = 0.0, ""
    for t in avoid:
        s = title_similarity(candidate, t)
        if s > best:
            best, hit = s, t
    return (best >= thresh, hit, best)

def tech_too_close(candidate: str, avoid: list[str]) -> tuple[bool, set[str]]:
    cand = _tech_labels(candidate)
    # if every avoided title shares same single label set, consider “too close”
    avoided = [_tech_labels(t) for t in avoid if t]
    if not avoided:
        return (False, cand)
    # if candidate's label set is subset of a common mode, mark close
    common = set.intersection(*avoided) if avoided else set()
    if common and cand & common:
        return (True, cand)
    return (False, cand)

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

settings = get_settings()

# ─── Client init (new SDK) ───────────────────────────────────
_client: genai.Client | None = None
try:
    # Picks up GEMINI_API_KEY from env or use explicit:
    _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    print("Gemini client initialized.")
except Exception as e:
    print(f"ERROR: Failed to init Gemini client: {e}")
    _client = None

# Strip ```json fences defensively
_fence = re.compile(r"^```(\w+)?\s*\n?(.*?)\n?```$", re.S)

# ─── 4. Tiny helper: hash prompt to stable cache key ──────────
def _hash_key(*parts) -> str:
    blob = json.dumps(parts, sort_keys=True, default=list).encode()
    return hashlib.sha256(blob).hexdigest()

# ─── 5. Async in-memory TTL cache (async-lru) ────────────────
@alru_cache(maxsize=settings.GEMINI_CACHE_MAXSIZE, ttl=settings.GEMINI_CACHE_TTL)
async def _cached_llm_call(cache_key: str, prompt: str):
    """
    Run the sync generate_content call in a worker thread so we don't block the event loop.
    """
    if _client is None:
        raise HTTPException(500, "Gemini client not initialized (check GEMINI_API_KEY)")
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=RECIPE_SCHEMA,
        temperature=settings.GEMINI_TEMP,
    )
    return await asyncio.to_thread(
        _client.models.generate_content,
        model=settings.GEMINI_MODEL_NAME,
        contents=prompt,
        config=cfg,
    )

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

    print(ingredients, cuisine, audience, servings, titles_to_avoid)
    avoid_list = titles_to_avoid or []
    prompt = PROMPT_TEMPLATE(ingredients, cuisine, audience, servings, titles_to_avoid)
    cache_key = _hash_key(ingredients, cuisine, audience, servings, titles_to_avoid)

    attempt_temps = [settings.GEMINI_TEMP, min(settings.GEMINI_TEMP + 0.2, 1.1), min(settings.GEMINI_TEMP + 0.4, 1.2)]
    last_reason = None

    MAX_ATTEMPTS = 3
    last_err: Optional[str] = None

    def _raise_http(status: int, msg: str):
        raise HTTPException(status_code=status, detail=msg)

    def _summarize_exc(e: Exception) -> str:
        cls = e.__class__.__name__
        status_code = getattr(e, "status", None) or getattr(e, "status_code", None)
        reason = getattr(e, "reason", None)
        extra = getattr(e, "message", None) or getattr(e, "detail", None) or ""
        return f"{cls} status={status_code} reason={reason} msg={str(e)} extra={extra}".strip()

    if _client is None:
        print("DEBUG_LLM_ERROR: _client is None. Check GEMINI_API_KEY.")
        _raise_http(500, "Gemini client not initialized (check API key)")

    for i, temp in enumerate(attempt_temps, start=1):
        cache_key = f"{cache_key}:{i}:{temp:.2f}"
        try:
            cfg = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RECIPE_SCHEMA,
                temperature=temp,
            )
            response = await asyncio.to_thread(
                _client.models.generate_content,
                model=settings.GEMINI_MODEL_NAME,
                contents=prompt,
                config=cfg,
            )
        except genai_errors.RateLimitError as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(429, "LLM rate limit/quota exceeded")
        except genai_errors.AuthenticationError as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(401, "Invalid or missing Gemini API key")
        except genai_errors.PermissionDeniedError as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(403, "Gemini permission denied (project/org)")
        except genai_errors.InvalidRequestError as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(400, f"Gemini invalid request: {e}")
        except genai_errors.SafetyError as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(412, "Blocked by safety filters for this prompt")
        except genai_errors.NotFoundError as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(404, "Gemini resource not found (check model name)")
        except genai_errors.APIConnectionError as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(503, "Upstream connectivity issue reaching Gemini")
        except genai_errors.APIStatusError as e:
            sc = getattr(e, "status_code", None) or getattr(e, "status", 502)
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            _raise_http(int(sc) if isinstance(sc, int) else 502, f"Gemini error: {e}")
        except Exception as e:
            print("DEBUG_LLM_ERROR:", _summarize_exc(e))
            traceback.print_exc()
            _raise_http(502, f"Gemini error (unclassified): {e}")

        raw = (response.text or "").strip()
        m = _fence.match(raw)
        if m:
            raw = m.group(2).strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            last_reason = f"bad json: {e}"
            continue

        # Model-reported error passes through
        if isinstance(parsed, dict) and "error" in parsed:
            return RecipeError(**parsed)

        # Validate + duplicate guard
        try:
            recipe = Recipe(**parsed)
        except Exception as e:
            last_err = f"Schema validation failed: {e}"
            continue

        dup, hit, score = too_similar(recipe.title, avoid_list, thresh=0.62)
        tech_close, cand_labels = tech_too_close(recipe.title, avoid_list)

        if dup or tech_close:
            print(f"DIVERSE_RETRY[{i}/{len(attempt_temps)}]: '{recipe.title}' ~ '{hit}' "
                  f"(sim={score:.2f}, tech_close={tech_close}, labels={cand_labels}); temp={temp}")
            last_reason = f"similar to '{hit}' (sim={score:.2f}) or tech-close={tech_close}"
            continue

        # ✅ passes diversity gates
        return recipe
    # All attempts failed → return a polite error so FE can auto re-roll once
    return RecipeError(error=f"Could not generate a sufficiently different recipe title. {last_reason or ''}".strip())
# ─── 7. Streaming generator (Server-Sent Events) ─────────────
async def stream_recipe_chunks(
        ingredients: List[str],
        cuisine: CuisineType,
        audience: AudienceType,
        servings: int,
        titles_to_avoid: Optional[List[str]] = None,
):
    """
    Simple async generator that *collects* streamed chunks on a worker thread
    and yields them back to the client. (If you want true live streaming,
    switch to a background task with an asyncio.Queue.)
    """
    if _client is None:
        raise HTTPException(500, "Gemini client not initialized")

    prompt = PROMPT_TEMPLATE(ingredients, cuisine, audience, servings, titles_to_avoid)
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=RECIPE_SCHEMA,
        temperature=settings.GEMINI_TEMP,
    )

    def _collect_stream():
        chunks = []
        for part in _client.models.generate_content_stream(
            model=settings.GEMINI_MODEL_NAME,
            contents=prompt,
            config=cfg,
        ):
            if part.text:
                chunks.append(part.text)
        return chunks

    # Run the stream collection off-thread, then yield chunks
    chunks = await asyncio.to_thread(_collect_stream)
    for c in chunks:
        yield {"event": "chunk", "data": c}
