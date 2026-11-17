# BookMySeat: Design Decisions

Each entry: what was decided, what else was considered, why, and the trade-off. Add new entries as the project grows. This file doubles as interview notes.

## Stack and setup

### 1. Django 5.2 LTS + DRF + simplejwt

- **Why:** LTS means long-term security support; DRF is the standard for Django APIs; simplejwt is the standard JWT library (built on PyJWT).
- **Rejected:** writing custom JWT handling with PyJWT. Hand-written auth is where subtle security bugs live (algorithm handling, expiry, revocation).

### 2. PostgreSQL from day 1

- **Why:** ACID transactions, row-level locks, CHECK and UNIQUE constraints, and relational data. SQLite silently ignores `select_for_update`, so concurrency tests would pass falsely.
- **Now:** local Postgres (`bookmyseat` database owned by `bookmyseat_master`, with CREATEDB for test databases). **Later:** Postgres 17 in Docker Compose.

### 3. Settings from environment variables (django-environ)

- **Why:** secrets and machine-specific values stay out of code; the same code runs locally, in Docker, and in production.
- **Rejected:** plain `os.environ` (everything is a string; `"False"` is truthy) and python-decouple (fine, but django-environ has database and cache URL helpers for Redis later).
- Types and defaults declared once in `environ.Env(...)`. Required values (`SECRET_KEY`, `DB_PASSWORD`) have no default, so startup fails loudly if missing.

### 4. Project structure

- Settings package named `bookmyseat`; apps `accounts`, `catalog`, `bookings`, `payments`, `core`.
- `core` stays flat (`camel_case.py`, `parsers.py`, `renderers.py`, `exceptions.py`, `error_codes.py`, `shortcuts.py`). Add folders only when several related files exist.
- Business logic lives in `services/` packages per app (plain functions), re-exported from `__init__.py` with `__all__`. Views stay thin.
- **Why:** flat is easier to navigate; re-exports let a file grow into a package without changing imports.

## Users and authentication

### 5. Custom user model before the first migrate

- `AbstractBaseUser`, email as `USERNAME_FIELD`, `AUTH_USER_MODEL = "accounts.User"`.
- **Why:** swapping the user model after migrations on a live database is a long, risky manual migration.

### 6. Roles via a `role` field (RBAC), no PermissionsMixin, no Django admin

- Roles: `super_admin`, `admin`, `staff`, `customer`. Checked by DRF permission classes reading `request.user.role`.
- **Rejected:** separate admin model (Django allows one user model), boolean flags like `is_admin` (can contradict each other), `PermissionsMixin` (its `is_superuser` would duplicate the `super_admin` role).
- No `is_staff`: only the Django admin uses it, and the admin is removed.
- Register never accepts `role` (mass-assignment protection).
- **Upgrade path:** Django Groups and permissions if roles need fine-grained rights (support can view orders but not refund).

### 7. Integer primary key + UUID `public_id`

- `id` (bigint) stays internal for fast joins; `public_id` (UUID4) is the only id exposed in URLs and tokens.
- **Why:** UUIDs can't be guessed or counted (enumeration protection, hides business volume).
- **Rejected:** encrypting ids (hashids): obfuscation with no security gain over UUIDs. UUID as primary key: random inserts fragment the index.
- Ownership is still checked on every query (`user=request.user`); a known `public_id` grants nothing.

### 8. No soft delete in the base model

- **Why:** every query would need to filter deleted rows forever; unique fields (email) stay occupied; most models never need it.
- **Users:** `is_active=False` to deactivate.
- **Account deletion (later):** anonymize the row (email becomes `deleted-<public_id>@deleted.invalid`, phone null, unusable password) so orders and payments stay intact and the person can sign up again.
- Orders store a buyer snapshot (name, email, phone at purchase time), which also serves legal and accounting retention.

### 9. Verification tracked separately from `is_active`

- `email_verified_at` and `phone_verified_at` (nullable timestamps, set explicitly with `timezone.now()`, never `auto_now`).
- **Why:** `is_active` means "allowed to log in at all". Mixing them makes a banned user look like an unverified one.
- **OTP (later):** codes in a separate table (hashed, 5–10 minute expiry, attempt limits, rate-limited sending). When a contact changes, the old one keeps working until the new one is verified.

### 10. Phone number: one E.164 field, optional

- `+919876543210` format, `null=True, blank=True, unique=True`.
- **Why:** one column makes uniqueness and lookups simple. NULL (not `""`) because Postgres allows many NULLs in a unique column but only one empty string.
- The register serializer rejects `""`.

### 11. Emails lowercased on write, exact-match lookups

- Manager lowercases the full email (Django's `normalize_email` only lowercases the domain).
- `get_by_natural_key` overridden to `email=username.lower()`; Django's default `ModelBackend` handles login (no custom backend).
- **Why:** `email__iexact` becomes `UPPER(email) = UPPER(...)`, which can't use the index on `email`.

### 12. JWT configuration

- Access token 15 minutes, refresh token 7 days, rotation on refresh, old refresh token blacklisted (`token_blacklist` app installed and migrated).
- `USER_ID_FIELD = "public_id"`: tokens don't expose internal ids.
- `CHECK_REVOKE_TOKEN = True`: a password change invalidates existing tokens.
- **Model: hybrid.** Access tokens verified statelessly (signature + expiry), user loaded from the database each request (so deactivation applies immediately); refresh tokens stateful (stored and revocable).
- **Known gap:** after logout, the access token works until it expires. **Later:** Redis deny-list of access token `jti` with TTL = remaining lifetime.
- JWTs are signed, not encrypted: never put secrets in claims.

### 13. Login methods

- **Email + password:** `POST /api/auth/login/` (simplejwt's view).
- **Phone (later):** OTP request + verify endpoints, tokens created with `RefreshToken.for_user(user)`.

## API conventions

### 14. JSON-only input

- **Why:** clients send JSON; JSON keeps types (numbers, booleans, null, nesting); one parser and code path; form encodings are what cross-site forms send.
- **File uploads (later):** `MultiPartParser` only on the upload views.

### 15. camelCase at the boundary, snake_case inside

- `CamelCaseJSONParser` converts incoming keys; the renderer converts outgoing keys. Conversion functions live once in `core/camel_case.py`.

### 16. Standard response format

- **Success:** `{"hasError": false, "message": null, "response": <data>}`.
- **Error:** `{"hasError": true, "status", "code", "message", "details": [{"field", "message"}], "response": null}`.
- `status` = HTTP status; `code` = machine-readable reason for the whole failure; `message` = one sentence for the user; `details` = field errors for form highlighting.
- The real HTTP status code is always correct (never 200 with an error).
- Codes live in `ErrorCode` (StrEnum) to prevent typos. Codes from DRF/simplejwt pass through unchanged.
- No success codes: outcomes like payment state live in the data (`order.status`).

### 17. Errors are raised, not returned

- Views and services raise exceptions; one exception handler formats them. No broad `except Exception`; unexpected errors become a 500 and are logged.
- `ConflictError` (409) for valid requests blocked by current state.
- **Status rules:**
  - 400 = fix your input
  - 401 = who are you
  - 403 = not allowed
  - 404 = doesn't exist (or isn't yours, to avoid revealing it)
  - 409 = state conflict (would have worked a minute ago)
  - 429 = rate limited
- User-facing messages are written deliberately; framework defaults are overridden where unclear. 404s use `get_object_or_not_found(queryset, message, **filters)`.

### 18. Secure by default

- Global `IsAuthenticated`; public endpoints declare `AllowAny` explicitly. Forgetting a permission class locks an endpoint instead of exposing it.

## Domain: movies with seat selection

### 19. Movies only, with seat selection

- **Why:** the project is BookMySeat; seat locking is the classic "Design BookMyShow" interview problem; theatre layouts are simple grids.
- **Rejected:** generic events with quantity-based ticket tiers (no seat choice).

### 20. Cities as a table

- `City(name, state, slug)`, unique `(name, state)`. Cinemas reference a city.
- **Why:** city names repeat across states; admins pick from a list instead of typing (no spelling mismatches); slugs give stable, readable filters.
- **Now:** filter by city slug. **Later:** radius search ("within 50 km") with PostGIS/GeoDjango. Cinemas already store latitude and longitude.

### 21. Catalog model

- `Movie` → `Show` (one movie, one screen, one time) → `Screen` → `Cinema` → `City`. `Seat` belongs to a screen (unique row + number per screen).
- `ShowPrice(show, category, price)`: prices vary per show and seat category.
- Money uses `DecimalField`, never floats.
- **Later:** exclusion constraint so shows can't overlap on the same screen.

### 22. Pre-created seat inventory (`ShowSeat`)

- One row per seat per show, created in bulk when the show is created: `show`, `seat`, `status` (available / held / booked), `held_by`, `held_until`; unique `(show, seat)`.
- **Rejected:** creating rows only on hold. Expired holds keep blocking the unique constraint until a cleanup job deletes them, so hold code needs "take over expired row" logic with extra race conditions.
- **Scale check:** about 200 rows per show; tens of thousands per cinema per week, which Postgres handles easily.

### 23. Holds: all-or-nothing conditional UPDATE in a transaction

- One `UPDATE ... WHERE show = ? AND seat IN (...) AND (status = 'available' OR (status = 'held' AND held_until < now()))`.
- If the updated row count is less than the number of seats requested, raise `ConflictError` inside `transaction.atomic()`, which rolls back everything.
- **Why:** Postgres row locks serialize concurrent updates to the same seat and re-check the condition, so exactly one user wins. Expiry is part of the condition, so no cleanup is needed for correctness.
- Holds happen before payment; payment only starts for seats already held by that user.
- **Proof:** concurrency test with many threads holding the same seat; exactly one succeeds.

### 24. Late payments (later)

- If payment arrives after the hold expired and the seat was taken, refund automatically.

## Design principles

- Build with common conventions first, improve later.
- Create an abstraction (ABC or Protocol) only when implementations vary: payment gateways (Razorpay/Stripe), OTP senders (email/SMS/console).
- Validate decisions with numbers (row counts, query plans) rather than intuition.
- The model defines what data can be; serializers define what each endpoint accepts.

## Parked for later

- OTP verification and phone login
- Logout endpoints (single device and all devices) and the Redis access-token deny-list
- Account deletion via anonymization
- File uploads (posters) with presigned URLs at scale
- Radius search with PostGIS
- Redis caching, rate limiting, Celery (hold cleanup, embeddings, token cleanup with `flushexpiredtokens`)
- Payments: order state machine, idempotency keys, webhook signature verification
- RAG: "Ask about this movie" with pgvector; natural-language search via tool calling
- Docker Compose, CI, deployment
- React frontend (movie list, seat map, booking)
