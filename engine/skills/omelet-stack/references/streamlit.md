# Recipe: Streamlit (internal tool or dashboard for a few people)

## When this recipe
A tool for the owner and a handful of colleagues: upload files, ask questions, see charts,
fill a form and get a result. One Python service, screens written as a script. Not for the
public and not for many users at once — then `fastapi-nextjs.md` or `django.md`.

## Services
- `app`: Python 3.12, Streamlit with run-on-save.
- SQLite in a volume when it must remember things; Postgres only if another product needs it.

## docker-compose.yml
```yaml
services:
  app:
    image: python:3.12-slim
    working_dir: /app
    command: sh -c "pip install -q -r requirements.txt && streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.runOnSave true --server.headless true"
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
    volumes:
      - .:/app
      - pip_cache:/root/.cache/pip
      - data:/data
volumes:
  pip_cache:
  data:
```

## .omelet/project.yml
```yaml
web:
  - service: app
    port: 8501
```

## First run
```bash
printf 'streamlit\npandas\n' > requirements.txt
printf 'import streamlit as st\nst.title("Hello")\n' > app.py
```
`.gitignore`: `__pycache__/`, `.env`, `.streamlit/secrets.toml`.

## Existing project
Use the project's own entry file in place of `app.py`; keep its `requirements.txt`.

## Gotchas
- `--server.address 0.0.0.0` and `--server.headless true` are both needed in a container.
- Streamlit streams over a websocket; Traefik passes it through. A page that loads and then
  shows "Please wait…" forever behind a proxy is the XSRF origin check — add
  `--server.enableXsrfProtection false` (fine inside the VM).
- Files the user uploads are in memory; write anything that must persist under `/data`.
- Keep the script short: one page per file under `pages/` once it grows past a screen.
