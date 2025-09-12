# DEV_NOTES — Recipify

Lightweight docs for running, deploying, and contributing. Bias toward shipping; keep this file short and accurate.

---

## 1) Overview
- **FE:** React + Vite + Tailwind
- **BE:** FastAPI + `google-genai` client
- **Auth:** Supabase
- **Goal (Phase 1):** ship a usable app; add rails for errors/logs/health; minimal diversity guard

---

## 2) Environment Variables

### Backend
- `GEMINI_API_KEY` — Google AI Studio key
- `GEMINI_MODEL_NAME` — e.g. `gemini-2.5-flash-lite` (or `gemini-2.5-flash`)
- `GEMINI_TEMP` — float, e.g. `0.7`

**Diversity/Cost knobs (Phase 1 defaults)**
- `DIVERSITY_MAX_ATTEMPTS_DEFAULT=1`
- `DIVERSITY_MAX_ATTEMPTS_REROLL=3`
- `DIVERSITY_SIM_THRESHOLD=0.62`
- `LOW_ENTROPY_ING_COUNT=3`
- `LOW_ENTROPY_MAX_ATTEMPTS=2`
- `VARIETY_WINDOW_DAYS=7`
- `VARIETY_PER_COMBO_CAP=32`
- `USE_EMBEDDINGS=false`

### Frontend
- `VITE_API_BASE_URL` — e.g. `https://api.example.com`

> Never commit `.env*` files. See `.gitignore`.

---

## 3) Run Locally

### Backend
```bash
# create venv + install
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# set env (example)
export GEMINI_API_KEY=...
export GEMINI_MODEL_NAME=gemini-2.5-flash-lite
export GEMINI_TEMP=0.7

# run
uvicorn main:app --reload
# health: http://localhost:8000/healthz, readiness: /readyz
