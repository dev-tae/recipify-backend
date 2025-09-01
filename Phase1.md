# 📦 Phase 1 Deployment Plan – Recipify

Goal: Get Recipify deployed and usable by real users in ~2 weeks.  
Approach: Ship fast, keep rails minimal, add learning as we go.

---

## ✅ Guiding Principles
- Bias toward shipping: shortcuts are fine if we note them.
- Keep consistent rails: error shape, request ID, basic logging.
- Use lightweight notes (`DEV_NOTES.md`) instead of heavy docs.
- Deploy early → dogfood → fix → learn.

---

## 📅 Timeline (14 Days)

### **Day 1–2: Backend Sanity Rails**
- [ ] Add consistent error shape: `{"error","code","trace"}`.
- [ ] Add req-id middleware + JSON logs.
- [ ] Add `/healthz` and `/readyz` routes.
- [ ] Test one endpoint end-to-end with FE.

### **Day 3–4: Minimal Diversity Guard**
- [ ] Implement in-memory per-combo avoid list (7-day TTL).
- [ ] Add lexical + structural duplicate check.
- [ ] Policy: 1 retry on first ask, 2 on re-roll, low-entropy guard.

### **Day 5: Frontend Fetch Wrapper**
- [ ] Replace direct `fetch` calls with `apiFetch` (sets `X-Req-Id`, parses errors).
- [ ] Add simple error toast/banner with `error` + `[trace …]`.

### **Day 6–7: Auth + Persistence Basics**
- [ ] Verify Supabase auth flow works.
- [ ] Store “cooked” and “saved” recipes (title + timestamp).
- [ ] Merge stored titles into avoid list pipeline.

### **Day 8–9: Environment & CI**
- [ ] Move secrets to `.env`.
- [ ] Add pre-commit hooks or run `black/ruff` once.
- [ ] Minimal GitHub Action: run `pytest` + `npm run build`.

### **Day 10–11: Deploy**
- [ ] FE → Vercel/Netlify.
- [ ] BE → Render/Fly.io/Heroku.
- [ ] Add CORS config.
- [ ] Smoke test `/healthz`.

### **Day 12–14: Dogfood + Fix**
- [ ] Use app daily.
- [ ] Invite 2–3 friends to try it.
- [ ] Log bugs/UX annoyances.
- [ ] Fix one per day.

---

## 📝 Lightweight Docs
- Keep `DEV_NOTES.md` updated with:
  - Env vars
  - Deployment steps
  - API summary
- Use commit messages for clarity (`feat: add diversity guard`).

---

## 🎯 Success Criteria
- Users can sign in, request recipes, re-roll, and avoid dupes.
- Logs show req-id + error shape consistently.
- App is deployed and accessible with minimal manual fixes.
