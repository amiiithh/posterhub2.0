# PosterHub

An online poster store built with **Python**, **Django** and **PostgreSQL**. Customers browse prints, pick a size, check out with coupons and review what they bought. Staff manage everything from a built-in control panel.

## Features

**Storefront**
- Cover-flow home page showing your posters, with search, category filter and price sort
- Poster pages with A4, A3 and A2 sizes (priced from one base price), specs and reviews
- Session-based cart, wishlist and a checkout form (Cash on delivery or simulated online payment)
- Coupons (percentage or flat, with minimum order, usage limit and expiry)
- Order history with cancellation, order confirmation email and a customer profile with saved address

**Reviews**
- Only customers who bought a poster (and did not cancel the order) can review it
- Readers can like reviews; the home page shows the top reviews, most-liked first
- Staff can hide a review at any time

**Staff panel (`/manage/`)**
- Dashboard with revenue, order status counts and best-selling posters
- Manage orders (status, notes, item quantities), posters (with image upload), categories, coupons, users and reviews

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Framework | Django 5 |
| Database | PostgreSQL (SQLite is available as a zero-setup fallback for a quick look) |
| Images | Pillow |
| Front end | Django templates, Tailwind CSS (CDN), Font Awesome |

## Getting started

### 1. Get the code and install dependencies

```bash
git clone https://github.com/amiiithh/posterhub2.0.git
cd posterhub2.0
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

```bash
createdb posterhub
```

or, in `psql`: `CREATE DATABASE posterhub;`

### 3. Point Django at PostgreSQL

Set these environment variables in the same terminal before running any `manage.py` command:

```powershell
# Windows PowerShell
$env:DB_ENGINE="postgres"
$env:DB_NAME="posterhub"
$env:DB_USER="postgres"
$env:DB_PASSWORD="your-password"
```

```bash
# macOS / Linux
export DB_ENGINE=postgres DB_NAME=posterhub DB_USER=postgres DB_PASSWORD=your-password
```

If `DB_ENGINE` is not set, the app uses a local SQLite file instead.

### 4. Create the tables, add sample data and run

```bash
python manage.py migrate
python manage.py seed            # sample categories, posters, coupons and an admin account
python manage.py runserver
```

Open http://127.0.0.1:8000/

The `seed` command creates:
- an admin user: **admin / admin123** (for local use only, change it or do not seed on a live site)
- the coupons `WELCOME15`, `STUDIO50` and `FESTIVE25`

### 5. Add your own posters

Log in as admin, open **/manage/posters/**, and add a poster with its image. Uploaded images are stored in `media/posters/`.

## Useful addresses

| Address | What it is |
|---|---|
| `/` | Home page |
| `/register/`, `/accounts/login/` | Sign up and log in |
| `/cart/`, `/checkout/`, `/orders/` | Shopping flow |
| `/wishlist/`, `/profile/` | Customer pages |
| `/manage/dashboard/` | Staff panel (staff users only) |
| `/admin/` | Django admin |

## Configuration

All settings come from environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `DEBUG` | `1` | Set to `0` in production |
| `SECRET_KEY` | development key | Must be a long random value in production |
| `ALLOWED_HOSTS` | any (debug only) | Comma-separated hostnames when `DEBUG=0` |
| `DB_ENGINE` | `sqlite` | `postgres` to use PostgreSQL |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | `posterhub`, `postgres`, empty, `127.0.0.1`, `5432` | PostgreSQL connection |
| `EMAIL_BACKEND` | console | Prints emails in the terminal; set an SMTP backend for real mail |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | see `settings.py` | SMTP details |

## Project structure

```
posterhub2.0/
├── manage.py
├── requirements.txt
├── posterhub/                  # Django project (settings, root URLs, wsgi/asgi)
└── shop/                       # The store app
    ├── models.py               # Category, Poster, Profile, Coupon, Order, OrderItem, Wishlist, Review
    ├── views.py                # Storefront views
    ├── views_admin.py          # Staff panel views
    ├── forms.py
    ├── urls.py
    ├── context.py              # Cart count and shared template data
    ├── admin.py                # Django admin setup
    ├── migrations/
    ├── management/commands/seed.py
    └── templates/              # All pages, including the staff panel
```

## Going live checklist

1. Set `DEBUG=0`, a strong `SECRET_KEY` and `ALLOWED_HOSTS`. With `DEBUG=0` the site redirects to HTTPS and sends HSTS headers.
2. Use PostgreSQL (`DB_ENGINE=postgres`) and set the `EMAIL_*` variables.
3. Run `python manage.py collectstatic`.
4. Serve `media/` (uploaded posters) from your web server or object storage. Django only serves it in debug mode.
5. Do not run `seed` on the live site, and change the admin password.

## Known limitations

- Online payment is simulated; there is no real payment gateway yet
- No automated tests
- Password-reset pages use Django's default look
- No rate limiting on login
- No file size limit on image uploads
- The home page lists all matching posters without pagination