# Residents table schema + indexes (PostgreSQL)

This repo’s backend expects these `residents` columns:

- `name` (required)
- `address` (required)
- `phone` (required)
- `email` (required)
- `photo_url` (optional)
- `building` (optional)
- `unit` (optional)
- timestamps (`created_at`, `updated_at`)

## How to apply (one statement at a time)

Connection example (from `resident_directory_database/db_connection.txt`):

```bash
psql postgresql://appuser:dbuser123@localhost:5000/myapp -c "SQL_STATEMENT"
```

### 1) Add columns if missing

```sql
ALTER TABLE residents ADD COLUMN IF NOT EXISTS building VARCHAR(100);
```

```sql
ALTER TABLE residents ADD COLUMN IF NOT EXISTS unit VARCHAR(50);
```

### 2) Indexes for filters + search

Filters / search patterns used by the backend:

- `unit`: exact match (`unit = :unit`) → btree index is effective
- `building`: partial match (`building ILIKE '%...%'`) → btree index helps only for exact/prefix; at scale prefer pg_trgm
- `q` (name search): (`name ILIKE '%...%'`) → at scale prefer pg_trgm
- `email`: case-insensitive exact (`lower(email)=lower(:email)`) → functional index is effective

Exact-match filters (building/unit):

```sql
CREATE INDEX IF NOT EXISTS ix_residents_building ON residents (building);
```

```sql
CREATE INDEX IF NOT EXISTS ix_residents_unit ON residents (unit);
```

Case-insensitive exact email filter:

```sql
CREATE INDEX IF NOT EXISTS ix_residents_email_lower ON residents (lower(email));
```

Optional (recommended at scale): trigram indexes for faster `ILIKE '%...%'` on name/building.

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

```sql
CREATE INDEX IF NOT EXISTS ix_residents_name_trgm ON residents USING gin (name gin_trgm_ops);
```

```sql
CREATE INDEX IF NOT EXISTS ix_residents_building_trgm ON residents USING gin (building gin_trgm_ops);
```

## Notes

- The backend uses `ILIKE` for text search and `lower(email)=lower(:email)` for the email filter.
- If you do not add `building`/`unit` columns, the backend will error at runtime when filtering/searching those fields.
