# PosterHub (Django)

## Run locally

### macOS / Linux (bash)

    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    python manage.py makemigrations shop
    python manage.py migrate
    python manage.py seed          # sample posters + admin / admin123
    python manage.py runserver     # http://127.0.0.1:8000  (admin: /admin/)

### Windows (cmd)

    py -3.10 -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python manage.py makemigrations shop
    python manage.py migrate
    python manage.py seed
    python manage.py runserver

### Windows (PowerShell)

    py -3.10 -m venv venv
    venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python manage.py makemigrations shop
    python manage.py migrate
    python manage.py seed
    python manage.py runserver

> **Note for Windows:** `source` is a bash command and does not work in cmd
> (use `venv\Scripts\activate` instead). If plain `python` points at an MSYS2 /
> MSYS or mingw build, PyPI wheels for Pillow may be unavailable and
> `pip install` will fail — create the venv with `py -3.10` (or another standard
> Windows Python) as shown above, or skip activation entirely and run
> `venv\Scripts\python manage.py ...`.

## PostgreSQL

The `psycopg2-binary` driver is already in `requirements.txt`. Create a database,
then set `DB_ENGINE=postgres` (and the connection vars) before migrate/seed/runserver:

    createdb posterhub        # or: CREATE DATABASE posterhub;
    export DB_ENGINE=postgres
    export DB_NAME=posterhub DB_USER=postgres DB_PASSWORD=... DB_HOST=127.0.0.1 DB_PORT=5432
    python manage.py migrate
    python manage.py seed
    python manage.py runserver

| Variable | Default | Notes |
| --- | --- | --- |
| `DB_ENGINE` | *(sqlite)* | Set to `postgres` to use PostgreSQL |
| `DB_NAME` | `posterhub` | Database name |
| `DB_USER` | `postgres` | Role |
| `DB_PASSWORD` | *(empty)* | Role password |
| `DB_HOST` | `127.0.0.1` | Server host |
| `DB_PORT` | `5432` | Server port |
| `DB_CONN_MAX_AGE` | `60` | Seconds to reuse a connection (0 = close each request) |

On Windows, use `set DB_ENGINE=postgres` in cmd or `$env:DB_ENGINE="postgres"` in
PowerShell instead of `export`.

### Move existing data from SQLite

Dump with the old (SQLite) settings, then load into PostgreSQL:

    # 1. With the default SQLite settings
    python manage.py dumpdata --natural-foreign --natural-primary \
      -e contenttypes -e auth.Permission -e sessions > data.json
    # 2. With DB_ENGINE=postgres set
    python manage.py migrate
    python manage.py loaddata data.json

## MySQL

Install mysqlclient, create a database, then set env vars before migrate:

    DB_ENGINE=mysql DB_NAME=posterhub DB_USER=root DB_PASSWORD=... DB_HOST=127.0.0.1

## Not done yet (SRS items for the next pass)

Payment gateway, password-reset emails, offers/discounts, admin sales charts,
product image upload UX, tests, production hardening (HTTPS, ALLOWED_HOSTS,
SECRET_KEY).
