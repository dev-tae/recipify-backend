from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn # For the if __name__ == "__main__": block
import os
from dotenv import load_dotenv
from routers import user_router, recipe_router, test_router
from core.config import init_supabase
import core.config

load_dotenv() # Load environment variables from .env file

app = FastAPI()
app.include_router(user_router.router)
app.include_router(recipe_router.router)
app.include_router(test_router.router)
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
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)) # Default to 8000 if PORT not set
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)