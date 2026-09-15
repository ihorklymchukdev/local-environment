# Recipe: Next.js (rich interactive app)

## When this recipe
Screens with real interaction — dashboards, editors, drag-and-drop, accounts — in one
language front and back. Also the front half of `fastapi-nextjs.md`, `payload.md` and
`medusa.md`.

## Services
- `web`: Node 22, `next dev` with reload.
- `db`: Postgres 16 when several people write or accounts exist; otherwise SQLite through
  Prisma with the file in a named volume.

## docker-compose.yml
```yaml
services:
  web:
    image: node:22-alpine
    working_dir: /app
    command: sh -c "npm install && npx next dev -H 0.0.0.0 -p 3000"
    environment:
      DATABASE_URL: postgresql://app:app@db:5432/app
    volumes:
      - .:/app
      - node_modules:/app/node_modules
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
  db_data:
```
Drop `db`, `depends_on` and `DATABASE_URL` for SQLite; then `DATABASE_URL: file:/data/app.db`
with a `data:/data` volume.

## .omelet/project.yml
```yaml
web:
  - service: web
    port: 3000
```

## First run
```bash
docker compose run --rm web npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --no-import-alias --use-npm --yes
docker compose run --rm web npm install prisma @prisma/client
docker compose run --rm web npx prisma init --datasource-provider postgresql
# after writing schema.prisma:
docker compose run --rm web npx prisma migrate dev --name init
```
Accounts: `npm install next-auth@beta` (Auth.js) — never a hand-written session or password
table. `.gitignore`: `node_modules/`, `.next/`, `.env*.local`.

## Existing project
Use the project's `dev` script: `npm run dev -- -H 0.0.0.0 -p 3000`. Read `.env.example` for
the variables it expects and put them in compose `environment`.

## Gotchas
- The page is opened through `http://<id>.127-0-0-1.sslip.io:39080`, not `localhost`. Next's
  dev server blocks its live-reload assets from other origins unless `next.config.ts` has
  `allowedDevOrigins: ["*.127-0-0-1.sslip.io"]`. Symptom: the page renders but never reloads,
  and the console shows a blocked `/_next/` request.
- `-H 0.0.0.0` is mandatory.
- Prisma's generated client is inside `node_modules`; after a schema change run
  `npx prisma generate` through compose, not on the VM.
