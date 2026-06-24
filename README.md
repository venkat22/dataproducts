# Data Products Registration Portal

A portal where teams register and catalog their data products. Fill the form
manually, or describe the data product in plain language and let the **AI
assistant** pre-fill it for you.

Each data product can also have a **data contract** — a lightweight, versioned
interface (schema fields, quality rules, and service-level objectives) loosely
aligned with the [Open Data Contract Standard](https://bitol.io/) concept. The
contract assistant can infer a schema from a pasted CSV header, JSON sample, or
plain-language description.

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
| GET    | `/api/data-products/{id}/contract` | Get a product's data contract |
| PUT    | `/api/data-products/{id}/contract` | Create or update the contract |
| DELETE | `/api/data-products/{id}/contract` | Delete the contract           |
| POST   | `/api/assist/contract`       | Infer schema/rules/SLOs from text |

Interactive API docs: http://localhost:8000/docs

## Project layout

```
backend/
  main.py        FastAPI app + routes (products, contracts, assist) + static serving
  models.py      SQLAlchemy models (DataProduct, DataContract)
  schemas.py     Pydantic schemas + allowed enum values
  database.py    Engine, session, startup table creation (with retry)
  ai_assist.py   Claude + fallback extraction for forms and contracts
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
