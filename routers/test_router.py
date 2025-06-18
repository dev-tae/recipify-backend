from fastapi import APIRouter, HTTPException
import google.genai as genai
from core.config import get_settings

router = APIRouter(prefix="/api/test", tags=["test"])

@router.get("/")
def test_gemini():
    settings = get_settings()
    try:
        model = genai.GenerativeModel(
            settings.GEMINI_MODEL_NAME,
            # api_key=settings.GEMINI_API_KEY,
        )
        response = model.generate_content("Say hello as a test!")
        return {"success": True, "response": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini test failed: {str(e)}")
