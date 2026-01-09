# resident-directory-management-system-303803-303821

## Environment configuration (previews / local)

### Backend (FastAPI) env vars
Set these in `resident_directory_backend/.env` (see `.env.example`):

- `DATABASE_URL` (required)
- `JWT_SECRET_KEY` (required)
- `JWT_ALGORITHM` (optional, default `HS256`)
- `ACCESS_TOKEN_EXPIRE_MINUTES` (optional, default `60`)
- `CORS_ALLOWED_ORIGINS` (optional, comma-separated). Default allows `http://localhost:3000`.
- `FRONTEND_PREVIEW_URL` (optional). If your preview platform provides a single frontend URL, you can set it here.

A lightweight diagnostics endpoint is available at:
- `GET /config/health` (no secrets returned)

### Frontend (React) env vars
Set these in `resident_directory_frontend/.env` (see `.env.example`):

- `REACT_APP_API_BASE_URL` (optional; defaults to `http://localhost:3001`)

Ensure the backend CORS allows the frontend origin you are using (local or preview URL).
