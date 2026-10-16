# PosterHub

A Django e-commerce storefront for archival wall-art posters, with a full custom admin panel.

---

## Feature Overview

| Module | What's included |
|---|---|
| **Storefront** | Home with search/filter/sort, product detail, gallery wall preview, lighting simulator |
| **Cart (Vault)** | Session-based cart, qty inc/dec/remove |
| **Checkout** | Shipping form, COD / Online payment, **coupon code apply**, order confirmation |
| **Orders** | Order history, cancel in-progress orders |
| **Wishlist** | Add/remove per-poster; dedicated wishlist page |
| **Profile** | Saved addresses, order stats, available coupons |
| **Reviews** | Leave a review after purchasing; star rating |
| **Custom Dashboard** (`/manage/`) | Analytics, orders, poster CRUD, categories, coupons, users, reviews |
| **Django Admin** (`/admin/`) | Full model-level admin with inline order items |

---

## Run locally (SQLite — zero config)

### Windows — PowerShell

```powershell
py -3.10 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed          # creates 12 sample posters + admin / admin123
python manage.py runserver     # http://127.0.0.1:8000
```

### Windows — Command Prompt

```cmd
py -3.10 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver
```

### macOS / Linux

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver
```

> **Windows note:** `source` is bash-only. Use `venv\Scripts\activate` (cmd) or `venv\Scripts\Activate.ps1` (PowerShell).

---

## Default credentials (after `seed`)

| Role | Username | Password | Access |
|---|---|---|---|
| Superuser | `admin` | `admin123` | Everything |

---

## URL map

| URL | Description |
|---|---|
| `/` | Storefront / home |
| `/poster/<id>/` | Product detail + reviews |
| `/cart/` | Vault (cart) |
| `/checkout/` | Checkout with coupon |
| `/orders/` | My orders |
| `/wishlist/` | My wishlist |
| `/profile/` | Account profile |
| `/accounts/login/` | Sign in |
| `/register/` | Register |
| `/manage/dashboard/` | **Custom analytics dashboard** |
| `/manage/orders/` | Staff order management |
| `/manage/posters/` | Poster CRUD |
| `/manage/categories/` | Category CRUD |
| `/manage/coupons/` | Coupon management |
| `/manage/users/` | User management (superuser only) |
| `/manage/reviews/` | Review moderation |
| `/admin/` | Django built-in admin |

---

## Coupon codes (seeded)

| Code | Type | Value | Min order |
|---|---|---|---|
| `WELCOME15` | % off | 15% | none |
| `STUDIO50` | flat INR | ₹500 off | ₹2,500 |
| `FESTIVE25` | % off | 25% | ₹1,500 |

---

## PostgreSQL

The `psycopg2-binary` driver is in `requirements.txt`. Create a database, then set `DB_ENGINE=postgres`:

```bash
createdb posterhub
export DB_ENGINE=postgres DB_NAME=posterhub DB_USER=postgres DB_PASSWORD=... DB_HOST=127.0.0.1 DB_PORT=5432
python manage.py migrate
python manage.py seed
python manage.py runserver
```

On Windows PowerShell: `$env:DB_ENGINE="postgres"` etc.

| Variable | Default | Notes |
|---|---|---|
| `DB_ENGINE` | *(sqlite)* | `postgres` or `mysql` |
| `DB_NAME` | `posterhub` | Database name |
| `DB_USER` | `postgres` | Role |
| `DB_PASSWORD` | *(empty)* | Role password |
| `DB_HOST` | `127.0.0.1` | Server host |
| `DB_PORT` | `5432` | Server port |
| `DB_CONN_MAX_AGE` | `60` | Seconds to reuse a connection |

### Migrate existing SQLite data to PostgreSQL

```bash
# 1. Dump from SQLite
python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.Permission -e sessions > data.json
# 2. Set DB_ENGINE=postgres, then:
python manage.py migrate
python manage.py loaddata data.json
```

---

## MySQL

```
DB_ENGINE=mysql DB_NAME=posterhub DB_USER=root DB_PASSWORD=... DB_HOST=127.0.0.1
```

Uncomment `mysqlclient` in `requirements.txt` before installing.

---

## Email

In development, emails are printed to the console (`EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`).
For production set `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` env vars.
