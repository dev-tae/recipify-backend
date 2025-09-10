# Recipify Backend

FastAPI service powering Recipify — an AI-powered recipe generator using Google’s Gemini models.

---

## 🚀 Run Locally

### 1. Create virtual environment & install deps
```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
2. Set environment variables
Create a .env file (never commit this):

ini
Copy code
GEMINI_API_KEY=your_key_here
GEMINI_MODEL_NAME=gemini-2.5-flash-lite
GEMINI_TEMP=0.7
DIVERSITY_MAX_ATTEMPTS_DEFAULT=1
DIVERSITY_MAX_ATTEMPTS_REROLL=3
3. Run the server
If main.py is at repo root:

bash
Copy code
uvicorn main:app --reload
If main.py is inside an app/ folder:

bash
Copy code
uvicorn app.main:app --reload
By default the server runs at http://127.0.0.1:8000

Health check: http://127.0.0.1:8000/healthz

Readiness: http://127.0.0.1:8000/readyz

📡 API Endpoints
POST /api/recipes/ → Generate recipe (JSON response)

POST /api/recipes/stream → Stream recipe chunks (SSE)

🧰 Dev Notes
Frontend expects VITE_API_BASE_URL pointing to this backend.

All responses return either:

json
Copy code
{ "title": "...", ... }
or error shape:

json
Copy code
{ "error": "message", "code": "CODE", "trace": "reqId" }
See DEV_NOTES.md for environment knobs and conventions.

yaml
Copy code

---

✅ This version will render properly on GitHub: headings, lists, and code blocks are clearly separated.  

Do you want me to also add a **Quickstart (3-liner TL;DR)** section at the very top so you don’t even need t