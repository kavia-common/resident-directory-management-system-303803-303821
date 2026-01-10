# Admins auth schema + seed + indexes (PostgreSQL)

This repo’s backend expects an `admins` table with refresh-token rotation metadata and a `role` column for RBAC.

## 1) Admins table (create if missing)

> Apply one statement at a time.

```sql
CREATE TABLE IF NOT EXISTS admins (
  id SERIAL PRIMARY KEY,
  username VARCHAR(255) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role VARCHAR(50) NOT NULL DEFAULT 'admin',
  refresh_token_hash TEXT NULL,
  refresh_token_version INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Optional: if you already have the table, add new columns safely:

```sql
ALTER TABLE admins ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT 'admin';
ALTER TABLE admins ADD COLUMN IF NOT EXISTS refresh_token_hash TEXT NULL;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS refresh_token_version INTEGER NOT NULL DEFAULT 0;
```

## 2) Indexes

`username` and `role` are queried frequently:

```sql
CREATE INDEX IF NOT EXISTS ix_admins_username ON admins (username);
CREATE INDEX IF NOT EXISTS ix_admins_role ON admins (role);
```

## 3) Seed an initial admin user

Because password hashes are bcrypt, seed via the helper command below or create the hash in Python.

### Option A (recommended): seed using a one-off Python snippet

Run this from within the backend environment (where `passlib[bcrypt]` is available):

```bash
python -c "from src.core.security import hash_password; print(hash_password('CHANGE_ME_STRONG_PASSWORD'))"
```

Then insert:

```sql
INSERT INTO admins (username, password_hash, role)
VALUES ('admin', 'BCRYPT_HASH_HERE', 'admin')
ON CONFLICT (username) DO NOTHING;
```

### Option B: if you already have an admin row

Update the role (if needed):

```sql
UPDATE admins SET role='admin' WHERE username='admin';
```

## 4) Refresh token rotation / revocation notes

This backend implements *single-device refresh token rotation* using:
- `admins.refresh_token_hash`: stores hash of the most recently issued refresh token
- `admins.refresh_token_version`: embedded into refresh JWT (`ver` claim); bumping it revokes all refresh tokens

Logout behavior:
- `POST /auth/logout` bumps `refresh_token_version` and clears `refresh_token_hash`

No separate token blacklist table is used in this implementation.

## 5) Recommended operational/security notes

- Ensure `JWT_SECRET_KEY` is long and random.
- Consider rate limiting the `/auth/login` endpoint at the edge (reverse proxy) for brute-force protection.
- Consider adding `updated_at` trigger for accurate updates if you rely on it at the DB layer.

