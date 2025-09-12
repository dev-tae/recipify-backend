from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn # For the if __name__ == "__main__": block
import os
from dotenv import load_dotenv
from routers import user_router, recipe_router, test_router
from core.config import init_supabase
import core.config
import time, uuid, json
from datetime import datetime, timezone
from typing import Any

load_dotenv() # Load environment variables from .env file

app = FastAPI()
app.include_router(user_router.router)
app.include_router(recipe_router.router)
app.include_router(test_router.router)


# --------- tiny helpers for rails ---------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_log(level: str, **fields: Any) -> None:
    print(json.dumps({"ts": _now_iso(), "level": level, **fields}), flush=True)


# central error shape
def _error_response(request: Request, *, status_code: int, error: str, code: str) -> JSONResponse:
    rid = getattr(request.state, "req_id", None) or "unknown"
    return JSONResponse(status_code=status_code, content={"error": error, "code": code, "trace": rid}, headers={"X-Req-Id": rid})


# CORS Configuration
# Adjust origins as needed for production
origins = [
    "http://localhost:3000",  # Common React dev port
    "http://localhost:5173",  # Common Vite dev port
    # Add your deployed frontend URL here later
    # e.g., "https://your-recipify-frontend.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Req-Id"],
    expose_headers=["X-Req-Id"],
)


@app.middleware("http")
async def _reqid_and_access_log(request: Request, call_next):
    # 1) assign/propagate req-id
    req_id = request.headers.get("X-Req-Id") or str(uuid.uuid4())
    request.state.req_id = req_id

    # 2) timing  path/method
    start = time.perf_counter()
    path = request.url.path
    method = request.method
    status = 500
    try:
        response = await call_next(request)
        status = getattr(response, "status_code", 500)
        return response
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        _json_log("info", reqId=req_id, method=method, path=path, status=status, latency=latency_ms)
        # always echo the req-id (even on exceptions handled later)
        try:
            response.headers["X-Req-Id"] = req_id  # will no-op if response not available
        except Exception:
            pass


# ---------- exception handlers: consistent error shape ----------
@app.exception_handler(HTTPException)
async def _http_exc_handler(request: Request, exc: HTTPException):
    return _error_response(request, status_code=exc.status_code, error=str(exc.detail), code=f"HTTP_{exc.status_code}")


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    _json_log("warn", reqId=getattr(request.state, "req_id", None), path=request.url.path, status=422, validationErrors=exc.errors())
    return _error_response(request, status_code=422, error="Validation failed", code="VALIDATION_ERROR")


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    _json_log("error", reqId=getattr(request.state, "req_id", None), path=request.url.path, status=500, msg=exc.__class__.__name__)
    return _error_response(request, status_code=500, error="Internal Server Error", code="INTERNAL_SERVER_ERROR")


# ---------------- Health & Readiness ----------------
@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "app": "recipify",
        "commit": os.getenv("GIT_SHA", "dev"),
        "time": _now_iso(),
    }


def _deps_status():
    deps = {}

    # Supabase (your init puts the client on core.config._supabase_backend_client)
    try:
        deps["db"] = "ok" if core.config._supabase_backend_client is not None else "not_initialized"
    except Exception:
        deps["db"] = "error"

    # Gemini API key presence (quick sanity; avoids doing a network call here)
    deps["gemini_key"] = "ok" if os.getenv("GEMINI_API_KEY") else "missing"

    return deps

@app.get("/readyz")
def readyz():
    deps = _deps_status()
    overall = "ready" if deps.get("db") == "ok" and deps.get("gemini_key") == "ok" else "degraded"
    return {"status": overall, "app": "recipify", "time": _now_iso(), "deps": deps}



@app.on_event("startup")
async def startup_event():
    print(">>> FastAPI application startup event triggered.")
    await core.config.init_supabase() # Call init_supabase via the module

    # Access the variable via the module to get its current state
    if core.config._supabase_backend_client:
        print(">>> FastAPI startup: core.config._supabase_backend_client SEEMS INITIALIZED after init_supabase() call.")
    else:
        print(">>> FastAPI startup: core.config._supabase_backend_client IS STILL NONE after init_supabase() call. CHECK CONFIG ERRORS.")
    print(">>> FastAPI application startup event finished.")


@app.get("/")
async def root():
    return {"message": "Welcome to Recipify API!"}


@app.get("/test")
async def test():
    global supabase_client
    # Now you can use `supabase_client` here!
    ...


# Example protected route placeholder
@app.get("/api/test-protected")
async def test_protected_route():
    # In a real scenario, you'd have a dependency here to check JWT
    return {"message": "If you see this, and it were protected, you'd be authenticated!"}


# Example error route to verify error shape quickly (remove later)
@app.get("/boom")
def boom():
    raise HTTPException(status_code=400, detail="Bad input example")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)) # Default to 8000 if PORT not set
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)