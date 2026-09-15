# Recipe: Laravel + Filament (business app with staff screens)

## When this recipe
Bookings, inventory, CRM-lite, forms with staff behind them, in the PHP ecosystem — the
right choice when the owner's hosting is PHP or the shape is "records + an admin".
Filament gives the admin screens; Breeze or Filament's own login gives accounts.

## Services
- `app`: PHP 8.3 with `artisan serve`, reload comes free (PHP reads files per request).
- `assets`: Node 22 running Vite in build-and-watch mode (rebuild on change; the page picks
  it up on refresh). No HMR server to route.
- `db`: MySQL 8 (Postgres is equally fine; keep what the owner's hosting offers).

## docker-compose.yml
```yaml
services:
  app:
    image: php:8.3-cli
    working_dir: /app
    command: php artisan serve --host=0.0.0.0 --port=8000
    environment:
      DB_CONNECTION: mysql
      DB_HOST: db
      DB_DATABASE: app
      DB_USERNAME: app
      DB_PASSWORD: app
    volumes:
      - .:/app
    depends_on:
      - db
  assets:
    image: node:22-alpine
    working_dir: /app
    command: sh -c "npm install && npm run build -- --watch"
    volumes:
      - .:/app
      - node_modules:/app/node_modules
  db:
    image: mysql:8
    environment:
      MYSQL_DATABASE: app
      MYSQL_USER: app
      MYSQL_PASSWORD: app
      MYSQL_ROOT_PASSWORD: root
    volumes:
      - db_data:/var/lib/mysql
volumes:
  node_modules:
  db_data:
```
`php:8.3-cli` lacks `pdo_mysql`; add a two-line `Dockerfile` (`FROM php:8.3-cli`,
`RUN docker-php-ext-install pdo_mysql`) and use `build: .` for `app`.

## .omelet/project.yml
```yaml
web:
  - service: app
    port: 8000
```

## First run
```bash
# composer is not a service in the compose file: plain `docker run` with the project mounted
docker run --rm -v "$PWD":/app -w /app composer:2 create-project laravel/laravel .
docker run --rm -v "$PWD":/app -w /app composer:2 require filament/filament:"^3.0"
docker compose run --rm app php artisan filament:install --panels --no-interaction
docker compose run --rm app php artisan migrate
docker compose run --rm app php artisan make:filament-user   # answers on the command line
```
Set `APP_URL` in `.env` to the URL `omelet up` printed. `.gitignore` comes with Laravel.

## Existing project
Keep the project's `composer.json` and `.env.example`; copy `.env.example` to `.env`, run
`docker run --rm -v "$PWD":/app -w /app composer:2 install`, `php artisan key:generate`, `migrate`.

## Gotchas
- `artisan serve` is a dev server; that is what we want here. Do not add nginx + php-fpm
  until the owner goes online.
- Filament resources (`app/Filament/Resources/`) are the admin screens: one per model the
  owner manages. Generate with `php artisan make:filament-resource <Model> --generate`.
- Vite in `--watch` mode does not hot-reload; the owner refreshes the page. Say so once.
