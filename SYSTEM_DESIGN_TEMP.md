**Recipify MVP - System Design Diagram (Textual Description)**

**Core Components:**

1.  **User (Client Browser):**
    *   Interacts with the Recipify Frontend.
    *   Initiates all actions.

2.  **Recipify Frontend (React App on Vercel):**
    *   **Hosted:** On Vercel (served as static assets + client-side JS).
    *   **Responsibilities:**
        *   Renders UI.
        *   Collects user input (ingredients, login credentials, etc.).
        *   Manages client-side state.
        *   Makes API calls to Supabase Auth directly for authentication actions.
        *   Makes API calls to Recipify Backend for application-specific logic.
    *   **Key Technologies:** React, TypeScript, Supabase JS Client, Fetch/Axios.

3.  **Recipify Backend (FastAPI on Vercel Serverless Functions):**
    *   **Hosted:** On Vercel (as Python serverless functions).
    *   **Responsibilities:**
        *   Handles business logic.
        *   Validates Supabase JWTs for protected routes.
        *   Interacts with Supabase PostgreSQL Database (CRUD operations).
        *   Interacts with Gemini API for recipe generation.
        *   Enforces generation limits and tier logic.
    *   **Key Technologies:** Python, FastAPI, Pydantic, Supabase Python Client (optional, or direct `psycopg2`), `python-jose` (for JWT if doing local validation later).

4.  **Supabase (Platform-as-a-Service):**
    *   **Supabase Authentication:**
        *   Handles user sign-up, sign-in (email/password, OAuth - e.g., Google).
        *   Issues JWTs.
        *   Manages `auth.users` table.
        *   Provides password reset, email verification flows.
    *   **Supabase PostgreSQL Database:**
        *   Stores all application data:
            *   `public.users` (app-specific user profiles, linked to `auth.users`).
            *   `public.recipes` (generated recipes).
            *   `public.user_recipes` (links users to recipes for history/saved).
            *   `public.user_kitchen_ingredients` (user's kitchen inventory).
        *   Handles database triggers (e.g., `handle_new_user`).

5.  **Gemini API (External Google Service):**
    *   **Responsibilities:**
        *   Accepts prompts from Recipify Backend.
        *   Generates recipe content in JSON format.
    *   Accessed via secure API key stored in Recipify Backend environment variables.

**Interactions & Data Flows:**

**(Arrows indicate direction of request/data flow)**

1.  **User Authentication (e.g., Email/Password Sign-In):**
    *   `User` -> `Recipify Frontend`: Enters email/password.
    *   `Recipify Frontend` -> `Supabase Auth`: Sends credentials using `supabase.auth.signInWithPassword()`.
    *   `Supabase Auth` -> `Recipify Frontend`: Returns JWT (and user session) on success.
    *   `Recipify Frontend`: Stores JWT securely (e.g., `localStorage` or Supabase session management).

2.  **User Authentication (e.g., Google OAuth Sign-In):**
    *   `User` -> `Recipify Frontend`: Clicks "Sign in with Google".
    *   `Recipify Frontend` -> `Supabase Auth`: Initiates OAuth flow (`supabase.auth.signInWithOAuth({ provider: 'google' })`).
    *   `Supabase Auth` -> `User (Browser)`: Redirects to Google for authentication.
    *   `User (Browser)` -> `Google`: User authenticates with Google.
    *   `Google` -> `Supabase Auth` (via redirect configured in Supabase): Confirms authentication.
    *   `Supabase Auth` -> `Recipify Frontend` (via redirect): Provides JWT/session.

3.  **Accessing a Protected Backend Route (e.g., Get User Profile `/api/users/me`):**
    *   `Recipify Frontend` -> `Recipify Backend`: Sends `GET /api/users/me` request with `Authorization: Bearer <SUPABASE_JWT>` header.
    *   `Recipify Backend`:
        *   Receives request, extracts JWT.
        *   *(Option 1: Backend calls Supabase to verify)* `Recipify Backend` -> `Supabase Auth`: Sends request to `/auth/v1/user` with the JWT to get user details & validate token.
        *   *(Option 2: Backend local JWT validation - future optimization)* Verifies JWT signature and claims locally using Supabase's public JWKS.
        *   If token is valid, extracts user ID (`sub` claim).
        *   `Recipify Backend` -> `Supabase PostgreSQL DB`: Queries `public.users` table using user ID.
    *   `Supabase PostgreSQL DB` -> `Recipify Backend`: Returns user data.
    *   `Recipify Backend` -> `Recipify Frontend`: Returns user profile JSON.

4.  **Recipe Generation Flow:**
    *   `User` -> `Recipify Frontend`: Selects ingredients, cuisine, etc., clicks "Generate".
    *   `Recipify Frontend` -> `Recipify Backend`: Sends `POST /api/recipes/generate` request with JWT and recipe parameters (ingredients, cuisine, etc.).
    *   `Recipify Backend`:
        *   Validates JWT (as in flow #3). Gets `user_id`.
        *   `Recipify Backend` -> `Supabase PostgreSQL DB`: Checks `public.users` for generation limits for `user_id`.
        *   If limits allow:
            *   Constructs prompt for Gemini.
            *   `Recipify Backend` -> `Gemini API`: Sends generation request.
    *   `Gemini API` -> `Recipify Backend`: Returns recipe JSON.
    *   `Recipify Backend`:
        *   Parses and validates recipe JSON.
        *   `Recipify Backend` -> `Supabase PostgreSQL DB`:
            *   Saves unique recipe to `public.recipes`.
            *   Adds entry to `public.user_recipes` (history for `user_id`).
            *   Updates `daily_generation_count` in `public.users`.
    *   `Supabase PostgreSQL DB` -> `Recipify Backend`: Confirms DB operations.
    *   `Recipify Backend` -> `Recipify Frontend`: Returns generated recipe JSON (or error).
    *   `Recipify Frontend`: Displays recipe to User.

5.  **Fetching Data (e.g., Recipe History):**
    *   `User` -> `Recipify Frontend`: Navigates to History tab.
    *   `Recipify Frontend` -> `Recipify Backend`: Sends `GET /api/recipes/history` request with JWT.
    *   `Recipify Backend`:
        *   Validates JWT. Gets `user_id`.
        *   `Recipify Backend` -> `Supabase PostgreSQL DB`: Queries `public.user_recipes` and `public.recipes` for the `user_id`.
    *   `Supabase PostgreSQL DB` -> `Recipify Backend`: Returns list of recipe data.
    *   `Recipify Backend` -> `Recipify Frontend`: Returns recipe list JSON.
    *   `Recipify Frontend`: Displays history.

**Diagram Layout Suggestions for Excalidraw:**

*   **Layers:**
    *   Top: User
    *   Next Layer: Recipify Frontend (React App on Vercel)
    *   Middle Layer: Recipify Backend (FastAPI on Vercel)
    *   Bottom/Side Layer: Supabase (Auth + DB), Gemini API
*   **Groupings:**
    *   You can draw a larger box around "Supabase" containing "Supabase Auth" and "Supabase PostgreSQL DB" boxes.
    *   You can draw a larger box around "Vercel" containing the "Recipify Frontend" and "Recipify Backend" boxes.
*   **Arrows:** Use different colors or line styles for different types of interactions if it helps (e.g., auth flow vs. data flow). Label arrows clearly (e.g., "1. Login Request (creds)", "2. JWT", "3. API Call (JWT, params)").
*   **Data Stores:** Use cylinder shapes for the PostgreSQL DB.
*   **External Services:** Use cloud shapes for Gemini API and potentially for Supabase as a whole platform.