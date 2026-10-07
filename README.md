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

## MySQL

Install mysqlclient, create a database, then set env vars before migrate:

    DB_ENGINE=mysql DB_NAME=posterhub DB_USER=root DB_PASSWORD=... DB_HOST=127.0.0.1

## Not done yet (SRS items for the next pass)

Payment gateway, password-reset emails, offers/discounts, admin sales charts,
product image upload UX, tests, production hardening (HTTPS, ALLOWED_HOSTS,
SECRET_KEY).
