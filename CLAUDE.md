# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AudioBookRequest is a lightweight FastAPI application for managing audiobook requests on media servers (Plex, Audiobookshelf, Jellyfin). It integrates with the Audible API for searching, Prowlarr for downloads, and provides user management with three permission groups: untrusted, trusted, and admin.

## Common Commands

### Development Setup
```bash
# Install dependencies and set up venv (uses uv instead of pip)
uv sync

# Initialize database (creates SQLite/Postgres and runs migrations)
just alembic_upgrade  # or: uv run alembic upgrade heads

# Run development server (includes auto-reload)
just dev  # or: uv run fastapi dev

# Start Tailwind CSS watcher for styling (in separate terminal)
just tailwind  # or: tailwindcss -i static/tw.css -o static/globals.css --watch

# Download DaisyUI components (required before first tailwind run)
just install_daisy
```

### Code Quality & Linting
```bash
# Run all checks (type checking, formatting, template linting, migrations)
just types  # or individually:
uv run basedpyright          # Type checking
uv run djlint templates      # Template linting
uv run ruff format --check app   # Format check
uv run alembic check         # Migration validation

# Database migrations
just create_revision "<message>"  # Auto-generate migration
# or: uv run alembic revision --autogenerate -m "<message>"

# Update dependencies
just upgrade  # or: uvx uv-upgrade
```

### Local Development Variants
- **VSCode**: Use the dev container settings in `.devcontainer/`
- **Docker Compose**: `docker compose --profile local up --build`
- **Environment variables**: Add to `.env.local` (takes precedence over `.env`)

## Architecture

### Core Components

**Frontend**: Jinja2 templates with Tailwind CSS + DaisyUI for styling. HTMX is used for dynamic interactions without heavy JavaScript.

**Backend**: FastAPI application structured into:
- `app/routers/` - Route handlers (split between UI templates and REST API)
  - `api/` - REST API endpoints (`/api` prefix)
  - Direct routes (`auth`, `root`, `search`, `settings`, `wishlist`) - HTML template responses
- `app/internal/` - Business logic and integrations
  - `auth/` - Authentication (basic, forms, OIDC) with session management
  - `book_search.py` - Audible API search, caching, and hybrid search with Google Books
  - `prowlarr/` - Integration with Prowlarr for searching indexers and triggering downloads
  - `models.py` - SQLModel ORM definitions
  - `notifications.py` - Apprise-based notification system
  - `ranking/` - Source ranking algorithm for download selection

**Database**: SQLModel (SQLAlchemy ORM with Pydantic) supporting SQLite (default) and PostgreSQL. Alembic for migrations.

**Configuration**: Pydantic Settings with environment variable prefixes (`ABR_*`) and nested delimiters (`__`). Reads from `.env`, `.env.local`, and environment.

### Data Model
- **User** - Username (PK), password, group (untrusted/trusted/admin), root admin flag
- **Audiobook** - ASIN (PK), title, authors, narrators, cover, duration. Cached from Audible. Includes ISBN and Google Books IDs for hybrid search.
- **AudiobookRequest** - Composite PK (ASIN + username). Links users to audiobooks they've requested.
- **ManualBookRequest** - For books not found on Audible (user-entered metadata)
- **Config** - Key-value store for settings (API keys, URLs, notification configs)
- **Notification** - Webhooks for events (new request, download success/failure)
- **APIKey** - For REST API authentication (separate from session auth)

### Key Workflows

**Search Flow**:
1. User searches from UI or API → `book_search.py:search_audiobooks()`
2. Check local cache first (with TTL-based expiration)
3. Query Audible API if needed
4. Optionally enhance with Google Books metadata (ISBN, extra info)
5. Return results with request counts and user's existing requests

**Download Flow**:
1. User requests audiobook (trusted/admin users trigger auto-download)
2. Store in `AudiobookRequest` table
3. If auto-download enabled: Query Prowlarr for sources
4. Rank sources using configurable heuristics (size, seeders, age, flags)
5. Send to download client via Prowlarr
6. Send notifications on completion/failure

**Authentication**:
- Session-based middleware in `session_middleware.py` validates user per request
- Supports basic auth, form login, and OIDC (with backup login at `/login?backup=1`)
- API key authentication available for `/api` endpoints
- Root admin credentials stored hashed in database

## Important Patterns

**Settings Access**: Use `Settings()` (from `env_settings.py`) to access configuration anywhere. It's a Pydantic BaseSettings class that reads environment variables.

**Database Sessions**: Get DB session via `next(get_session())` from `app/util/db.py`. Always use context manager (`with`) to ensure cleanup.

**Error Handling**:
- `RequiresLoginException` - Redirects GET requests to login, returns 401 for non-GET
- `InvalidOIDCConfiguration` - Redirects to error page
- `ToastException` - Shows user-facing toast messages

**Async Code**: Most I/O (API calls, database) is async. Use `aiohttp.ClientSession` for HTTP, SQLModel works with async sessions.

**Type Checking**: Uses `basedpyright` with `typeCheckingMode = "all"`. Avoid untyped libraries (allowlist in `pyproject.toml`).

## Database Notes

Alembic migrations are tracked in `alembic/versions/`. When modifying ORM models, generate migrations with `just create_revision`:
```bash
just create_revision "Add new field to Audiobook"
```

**PostgreSQL**: Migrations may need manual unique constraint additions (Alembic limitation).

Use `uv run alembic check` before committing to validate migration integrity.

## Testing

There are no dedicated unit tests. Validate changes with:
- Type checking: `uv run basedpyright`
- Template linting: `uv run djlint templates`
- Code formatting: `uv run ruff format app` (and check with `--check`)
- Manual testing: `just dev` and visit http://localhost:9000

## Code Style

- **Conventional Commits**: Follow [Conventional Commits](https://www.conventionalcommits.org) (e.g., `feat:`, `fix:`, `refactor:`, `docs:`)
- **Formatting**: Ruff handles formatting. Use `uv run ruff format app` to auto-fix.
- **Type annotations**: Required by basedpyright. Use proper return types and parameter annotations.
- **Naming**: Use snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants.

## Key Dependencies

- **FastAPI** - Web framework and API docs
- **SQLModel** - ORM combining SQLAlchemy + Pydantic
- **Alembic** - Database migrations
- **Jinja2 + jinja2-fragments** - Templating for HTMX
- **APScheduler** - Scheduled tasks
- **Pydantic** - Data validation and settings
- **structlog** - Structured logging
- **Argon2** - Password hashing
- **cryptography** - JWT and encryption
