# Recipe: Payload CMS (custom site with an editing screen, one codebase)

## When this recipe
A content site whose front must look and behave exactly as the owner wants, plus an editing
screen for a non-technical person — and WordPress's themes are not the right fit. Payload 3
runs inside Next.js: one service, admin at `/admin`, the public pages in the same app.

## Services
- `web`: Node 22, Next.js with Payload.
- `db`: Postgres 16 (Payload's Postgres adapter); SQLite adapter for a single editor.

## docker-compose.yml
```yaml
services:
  web:
    image: node:22-alpine
    working_dir: /app
    command: sh -c "npm install && npx next dev -H 0.0.0.0 -p 3000"
    environment:
      DATABASE_URI: postgresql://app:app@db:5432/app
      PAYLOAD_SECRET: change-me-in-env
    volumes:
      - .:/app
      - node_modules:/app/node_modules
      - media:/app/media
    depends_on:
      - db
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes:
      - db_data:/var/lib/postgresql/data
volumes:
  node_modules:
  media:
  db_data:
```

## .omelet/project.yml
```yaml
web:
  - service: web
    port: 3000
```

## First run
```bash
docker compose run --rm web npx create-payload-app@latest . --template website --db postgres --use-npm --no-git -y
```
The first visit to `<URL>/admin` creates the first user; do it yourself, write the address,
user and password down for the owner and tell them to change the password. Collections
(`src/collections/`) are the things the owner edits; one per kind of content.
`.gitignore`: `node_modules/`, `.next/`, `media/`, `.env`.

## Existing project
Use the project's `dev` script with `-H 0.0.0.0`; read `.env.example` for `DATABASE_URI`
and `PAYLOAD_SECRET`.

## Gotchas
- Same live-reload origin rule as `nextjs.md`: `allowedDevOrigins: ["*.127-0-0-1.sslip.io"]`.
- After changing a collection, Payload writes a migration in dev automatically; commit it.
- Uploaded media lives in the `media` volume, not in git.
