# Recipe: Astro (static site)

## When this recipe
Landing page, portfolio, brochure site, docs — content the owner changes rarely and through
you. No accounts, nothing remembered. If someone non-technical edits weekly, use
`wordpress.md` or `payload.md` instead.

## Services
- `web`: Node 22, Astro dev server with reload. No database.

## docker-compose.yml
```yaml
services:
  web:
    image: node:22-alpine
    working_dir: /app
    command: sh -c "npm install && npx astro dev --host 0.0.0.0 --port 4321"
    volumes:
      - .:/app
      - node_modules:/app/node_modules
volumes:
  node_modules:
```

## .omelet/project.yml
```yaml
web:
  - service: web
    port: 4321
```

## First run
```bash
docker compose run --rm web npm create astro@latest -- . --template minimal --no-install --no-git --yes
docker compose run --rm web npm install
docker compose run --rm web npm install -D tailwindcss @tailwindcss/vite   # if styling with Tailwind
```
`.gitignore`: `node_modules/`, `dist/`, `.astro/`.

## Existing project
Keep the project's own `package.json`; only the compose file and `project.yml` are new. If
`package.json` has a `dev` script, use `npm run dev -- --host 0.0.0.0 --port 4321` instead of
calling `astro` directly.

## Gotchas
- `--host 0.0.0.0` is mandatory; without it the dev server answers only inside the container
  and the URL never loads.
- `node_modules` lives in a named volume so the image's Linux build of native modules is never
  mixed with anything else; the first start runs `npm install` and takes a minute.
- Content collections (`src/content/`) are the right place for anything list-like (projects,
  team, posts) so the owner's words are data, not markup.
