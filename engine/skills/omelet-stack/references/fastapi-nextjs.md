# Recipe: FastAPI + Next.js (smart app that processes documents or data)

## When this recipe
The brief needs Python (reading PDFs, embeddings, analysis, ML) and a real web front for
customers or a team. For a few internal users, `streamlit.md` is one service instead of two.
For a chat feature that is only model calls, `nextjs.md` with the AI SDK is enough.

## Services
- `api`: Python 3.12, uvicorn with reload, port 8000 — the only place documents are handled.
- `web`: Node 22, Next.js — the screens; talks to `api` through a server-side rewrite so the
  owner has one URL.
- `db`: Postgres 16 with `pgvector` when documents are searched by meaning.

## docker-compose.yml
```yaml
services:
  web:
    image: node:22-alpine
    working_dir: /app/web
    command: sh -c "npm install && npx next dev -H 0.0.0.0 -p 3000"
    environment:
      API_URL: http://api:8000
    volumes:
      - .:/app
      - web_modules:/app/web/node_modules
    depends_on:
      - api
  api:
    image: python:3.12-slim
    working_dir: /app/api
    command: sh -c "pip install -q -r requirements.txt && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    environment:
      DATABASE_URL: postgresql+psycopg://app:app@db:5432/app
      # the model provider's key under the name its library reads, e.g. ANTHROPIC_API_KEY
      # or OPENAI_API_KEY; which provider is a decision recorded in docs/stack.md
      <PROVIDER>_API_KEY: ${<PROVIDER>_API_KEY:-}
    volumes:
      - .:/app
      - pip_cache:/root/.cache/pip
      - uploads:/data/uploads
    depends_on:
      - db
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes:
      - db_data:/var/lib/postgresql/data
volumes:
  web_modules:
  pip_cache:
  uploads:
  db_data:
```
Layout: `web/` (Next.js) and `api/` (FastAPI) side by side in the project folder.

## .omelet/project.yml
```yaml
web:
  - service: web
    port: 3000
```
The API is not listed: the browser never talks to it directly. In `web/next.config.ts`:
```ts
rewrites: async () => [{ source: "/api/:path*", destination: `${process.env.API_URL}/:path*` }]
```

## First run
```bash
mkdir -p web api/app
docker compose run --rm -w /app/web web npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --no-import-alias --use-npm --yes
printf 'fastapi\nuvicorn[standard]\npython-multipart\nsqlalchemy\npsycopg[binary]\npgvector\npypdf\n' > api/requirements.txt
```
Write `api/app/main.py` with a `/health` route first and check it through the rewrite
(`curl <URL>/api/health`) before any feature. Model keys come from the owner and go into a
`.env` file next to the compose file, never into code. `.gitignore`: `node_modules/`,
`.next/`, `__pycache__/`, `.env`.

## Existing project
Two folders with their own manifests usually already exist; keep their names and adjust
`working_dir`. Read the API's `.env.example` for the variables it expects.

## Gotchas
- `--reload` in uvicorn watches the mounted source; it does not watch `requirements.txt` —
  restart the service after adding a package.
- Uploads go in the `uploads` volume, not the source tree; a mounted source full of PDFs
  slows every reload.
- The owner needs a model key for the smart part. Ask for it in plain words ("a key from the
  AI provider's website"), and build and demo everything else first so the URL works without it.
