# Data Products Registration Portal

A portal where teams register and catalog their data products. Fill the form
manually, or describe the data product in plain language and let the **AI
assistant** pre-fill it for you.

## Stack

- **Backend** — FastAPI + SQLAlchemy, serving a REST API and the static frontend
- **Database** — PostgreSQL
- **Frontend** — self-contained single-page app (no build step)
- **AI assistant** — Claude API (`anthropic`), with a local keyword-extraction
  fallback so the portal works fully offline

## Run locally

```bash
# optional: enable the Claude-powered assistant
cp .env.example .env   # then add your ANTHROPIC_API_KEY

docker compose up --build
```

Open http://localhost:8000

Without an `ANTHROPIC_API_KEY`, the AI assistant runs in **local mode** and
extracts fields with keyword heuristics. With a key set, it uses Claude.

## API

| Method | Path                         | Description                       |
|--------|------------------------------|-----------------------------------|
| GET    | `/api/health`                | Health + whether AI is enabled    |
| GET    | `/api/options`               | Allowed enum values for the form  |
| GET    | `/api/data-products`         | List all data products            |
| POST   | `/api/data-products`         | Create a data product             |
| GET    | `/api/data-products/{id}`    | Get one                           |
| PUT    | `/api/data-products/{id}`    | Update                            |
| DELETE | `/api/data-products/{id}`    | Delete                            |
| POST   | `/api/assist`                | Turn free text into form fields   |

Interactive API docs: http://localhost:8000/docs

## Project layout

```
backend/
  main.py        FastAPI app + routes + static serving
  models.py      SQLAlchemy model
  schemas.py     Pydantic schemas + allowed enum values
  database.py    Engine, session, startup table creation (with retry)
  ai_assist.py   Claude + fallback field extraction
  config.py      Settings (env-driven)
  Dockerfile
frontend/
  index.html, styles.css, app.js
docker-compose.yml
```

## Stopping

```bash
docker compose down        # keep data
docker compose down -v     # also wipe the database volume
```
