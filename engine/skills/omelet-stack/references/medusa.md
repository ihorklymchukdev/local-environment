# Recipe: Medusa (shop where the shopping experience is custom)

## When this recipe
A shop whose storefront must be designed from scratch (brand-heavy, unusual flows) with a
proper admin for products, orders and payments behind it. For a shop the owner mainly edits
from an admin, `woocommerce.md` is one service and finished sooner.

## Services
- `backend`: Node 22, Medusa server with the admin at `/app`, port 9000.
- `storefront`: Node 22, the Next.js starter, port 8000.
- `db`: Postgres 16. `redis`: Redis 7 (events, sessions).

## docker-compose.yml
```yaml
services:
  storefront:
    image: node:22-alpine
    working_dir: /app/storefront
    command: sh -c "npm install && npm run dev -- -H 0.0.0.0 -p 8000"
    environment:
      MEDUSA_BACKEND_URL: http://backend.<project-id>.127-0-0-1.sslip.io:39080
      NEXT_PUBLIC_MEDUSA_BACKEND_URL: http://backend.<project-id>.127-0-0-1.sslip.io:39080
    volumes:
      - .:/app
      - store_modules:/app/storefront/node_modules
    depends_on:
      - backend
  backend:
    image: node:22-alpine
    working_dir: /app/backend
    command: sh -c "npm install && npm run dev"
    environment:
      DATABASE_URL: postgres://app:app@db:5432/app
      REDIS_URL: redis://redis:6379
      STORE_CORS: http://<project-id>.127-0-0-1.sslip.io:39080
      ADMIN_CORS: http://backend.<project-id>.127-0-0-1.sslip.io:39080
      AUTH_CORS: http://<project-id>.127-0-0-1.sslip.io:39080,http://backend.<project-id>.127-0-0-1.sslip.io:39080
      JWT_SECRET: change-me
      COOKIE_SECRET: change-me
    volumes:
      - .:/app
      - back_modules:/app/backend/node_modules
    depends_on:
      - db
      - redis
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes:
      - db_data:/var/lib/postgresql/data
  redis:
    image: redis:7-alpine
volumes:
  store_modules:
  back_modules:
  db_data:
```
Replace `<project-id>` with the id `omelet up` prints (the folder name, lower-case).

## .omelet/project.yml
```yaml
web:
  - service: storefront
    port: 8000
  - service: backend
    port: 9000
```
The first entry keeps the bare project host; the second gets the `backend.` prefix — that is
why the URLs above are spelled that way.

## First run
```bash
docker compose run --rm -w /app backend npx create-medusa-app@latest backend --with-nextjs-starter --db-url postgres://app:app@db:5432/app --no-browser
# the starter lands in backend/ and backend-storefront/; move the latter to storefront/
docker compose run --rm backend npx medusa db:migrate
docker compose run --rm backend npx medusa user -e owner@example.com -p <generate one>
```
Admin at `http://backend.<project-id>.127-0-0-1.sslip.io:39080/app`. Write it down for the
owner. Payments: the Stripe provider module, keys entered in `.env`, never in code.
`.gitignore`: `node_modules/`, `.next/`, `.medusa/`, `.env`.

## Existing project
Two folders usually exist already; keep their names in `working_dir` and read each
`.env.template`.

## Gotchas
- Every CORS variable must name the exact URL the browser uses, port included; a storefront
  that loads but shows no products is CORS.
- Medusa's dev server takes a minute to start the first time; poll the backend's `/health`.
- Publishable API key: the storefront needs one from the admin (Settings → Publishable API
  keys) in `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY`.
