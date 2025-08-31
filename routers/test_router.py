# routers/test_router.py
import os
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/test", tags=["test"])

# ---- config ----
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY or GOOGLE_API_KEY in environment.")

# ---- minimal compat layer for the two SDKs ----
# We build a single callable: sync_generate(prompt) -> str
sync_generate = None

try:
    # NEW SDK (google-genai)
    # pip install google-genai
    from google import genai as _genai_new

    _client = _genai_new.Client(api_key=API_KEY)

    def _gen_new(prompt: str) -> str:
        # new SDK is synchronous; call directly
        resp = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        # 'text' is a convenience property returning concatenated parts
        return getattr(resp, "text", str(resp))

    sync_generate = _gen_new
except Exception:
    try:
        # OLD SDK (google-generativeai)
        # pip install google-generativeai
        import google.generativeai as _genai_old

        _genai_old.configure(api_key=API_KEY)
        _model = _genai_old.GenerativeModel(MODEL_NAME)

        def _gen_old(prompt: str) -> str:
            resp = _model.generate_content(prompt)
            return getattr(resp, "text", str(resp))

        sync_generate = _gen_old
    except Exception as e:
        raise RuntimeError(
            "Could not import a Google Gemini SDK. "
            "Install either 'google-genai' (new) or 'google-generativeai' (old)."
        ) from e


@router.get("/", summary="Quick Gemini smoke test")
async def test_gemini():
    """
    Calls the model with a trivial prompt to verify:
    - API key is loaded,
    - the model name is valid,
    - SDK import is correct,
    - outbound network works.
    """
    try:
        text = await run_in_threadpool(lambda: sync_generate("Say a short hello."))
        return {"ok": True, "model": MODEL_NAME, "message": text}
    except Exception as e:
        # Surface the exact error in dev to speed up debugging
        raise HTTPException(status_code=500, detail=f"Gemini call failed: {e!s}")
