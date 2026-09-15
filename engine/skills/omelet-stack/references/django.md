# Recipe: Django (business app or data app with an admin)

## When this recipe
Records, forms and staff screens in the Python ecosystem — the right choice when documents
or data are processed as well, or when the brief is mostly "an admin for our things".
The Django admin is the editing screen; `django-allauth` is the accounts library.

## Services
- `web`: Python 3.12, `runserver` (reloads on change).
- `db`: Postgres 16 when several people write; SQLite in a volume for one or two.

## docker-compose.yml
```yaml
services:
  web:
    image: python:3.12-slim
    working_dir: /app
    command: sh -c "pip install -q -r requirements.txt && python manage.py runserver 0.0.0.0:8000"
    environment:
      DATABASE_URL: postgres://app:app@db:5432/app
      DJANGO_DEBUG: "1"
    volumes:
      - .:/app
      - pip_cache:/root/.cache/pip
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
  pip_cache:
  db_data:
```
SQLite: drop `db`; set `DATABASE_URL: sqlite:////data/db.sqlite3` with a `data:/data` volume.

## .omelet/project.yml
```yaml
web:
  - service: web
    port: 8000
```

## First run
```bash
printf 'Django>=5.1,<6\ndj-database-url\npsycopg[binary]\ndjango-allauth\n' > requirements.txt
docker compose run --rm web sh -c "pip install -r requirements.txt && django-admin startproject config ."
# in config/settings.py: ALLOWED_HOSTS = ["*"] (dev only), DATABASES from dj_database_url
docker compose run --rm web python manage.py migrate
docker compose run --rm -e DJANGO_SUPERUSER_PASSWORD=<generate one> web \
  python manage.py createsuperuser --noinput --username owner --email owner@example.com
```
Write the admin address (`<URL>/admin/`), user and password down for the owner.
`.gitignore`: `__pycache__/`, `*.sqlite3`, `.env`, `media/`.

## Existing project
Keep `requirements.txt` (or install from `pyproject.toml` with `pip install -e .`). Read
`settings.py` for the database it expects and the `ALLOWED_HOSTS`; the sslip host must be
allowed or every request is a 400.

## Gotchas
- `ALLOWED_HOSTS` must include the sslip host (`["*"]` in the VM is fine). A blank page with
  "DisallowedHost" in `omelet logs` is this.
- `runserver 0.0.0.0:8000` — the address is mandatory.
- Migrations are committed files; make them through compose
  (`docker compose run --rm web python manage.py makemigrations`) and commit them with the
  model change.
- Document processing (PDF text, embeddings) goes in this service or a `worker` service with
  the same image; never on the VM.
