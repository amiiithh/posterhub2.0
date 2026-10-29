# PosterHub

An online poster store built with **Python**, **Django** and **PostgreSQL**. Customers browse prints, pick a size, check out with coupons and review what they bought. Staff manage everything from a built-in control panel.

## Features

**Storefront**
- Cover-flow home page that features your best-selling posters (best seller in the centre), with search, category filter and price sort below
- Poster pages with A4, A3 and A2 sizes (priced from one base price), specs and reviews
- The Vault (cart) belongs to your account: it is saved in the database, follows you to any browser or device, and is never shown to the next person who uses the same computer (signing out clears the browser). Items added before signing in are merged into your Vault when you sign in. Also a wishlist and a checkout form (Cash on delivery or simulated online payment)
- Coupons (percentage or flat, with minimum order, usage limit, expiry and an optional first-order-only rule)
- After checkout the customer lands on an invoice (invoice number, items, coupon discount, totals, payment method and shipping details) that can be printed or saved as PDF, and the same details are emailed (sign-up asks for an email address)
- Order history shows each order with a progress tracker (Processing, Shipped, Delivered), its items with pictures, price breakdown, shipping address and a link to the invoice, with a status filter, paging and cancellation while an order is Processing. Poster titles are saved on each order line, so old orders and invoices stay correct even if a poster is renamed or deleted
- A customer profile with a saved address
- A redesigned sign-in page with a Show/Hide password button, a Caps Lock warning, a "Forgot password?" link, and it takes you back to the page you were trying to reach. The password is never printed back into the page after a failed attempt
- Checkout, cart and review forms are validated, and an order is saved all-or-nothing, so a failure never leaves a half-created order
- The shop grid is paginated (12 posters per page)
- Uploaded poster images are resized (longest side 1400 px) and compressed automatically; uploads over 10 MB are refused
- Order rules: status moves forward only (Processing, Shipped, Delivered, or Cancelled), quantities can be edited only while an order is Processing and the total updates with them, and cancelling an order gives its coupon use back

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
| Front end | Django templates, Tailwind CSS and Font Awesome (both loaded from CDNs, so the pages need an internet connection) |

## Getting started

### 1. Get the code and install dependencies

```bash
git clone https://github.com/amiiithh/posterhub2.0.git
cd posterhub2.0
py -m venv venv                  # Windows (use the python.org Python)
venv\Scripts\activate
# python3 -m venv venv           # macOS / Linux
# source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

```bash
createdb posterhub
```

or, in `psql` or pgAdmin: `CREATE DATABASE posterhub;` (on Windows, `createdb` only works if PostgreSQL's `bin` folder is on your PATH)

### 3. Point Django at PostgreSQL

Set these environment variables in the same terminal before running any `manage.py` command:

```bat
:: Windows Command Prompt
set DB_ENGINE=postgres
set DB_NAME=posterhub
set DB_USER=postgres
set DB_PASSWORD=your-password
```

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
python manage.py seed            # sample categories, posters and coupons (plus a development admin, see below)
python manage.py runserver
```

Open http://127.0.0.1:8000/

The `seed` command creates:
- in development (when you start the project with `python manage.py ...`), an admin user: **admin / admin123**
- on a live site no admin is created unless you ask: `python manage.py seed --admin-password "a-strong-password"` (or set `ADMIN_PASSWORD`), or use `python manage.py createsuperuser`
- the coupons `WELCOME15` (first order only), `STUDIO50` and `FESTIVE25`

### 5. Add your own posters

Log in as admin, open **/manage/posters/**, and add a poster with its image. Uploaded images are stored in `media/posters/`.

## Running the server

After the first-time setup above, this is all you need each time you come back to the project.

1. Open a terminal in the project folder (the one that contains `manage.py`).
2. Activate the virtual environment. You should see `(venv)` at the start of the line.
   ```bash
   venv\Scripts\activate            # Windows
   # source venv/bin/activate       # macOS / Linux
   ```
3. If you use PostgreSQL, set the `DB_*` variables again (see step 3 above). They only last for that terminal window.
4. If you pulled new code, update the database first:
   ```bash
   python manage.py migrate
   ```
5. Start the server:
   ```bash
   python manage.py runserver
   ```
6. Open http://127.0.0.1:8000/ in your browser.
7. Stop the server with `Ctrl + C`.

**Other ways to run it**

```bash
python manage.py runserver 8080            # use a different port
python manage.py runserver 0.0.0.0:8000    # also reachable from a phone on the same Wi-Fi
```

For the second command, find your PC's IP with `ipconfig` (Windows) or `ifconfig` (macOS / Linux), allow it before starting the server (for example `set ALLOWED_HOSTS=192.168.1.5` in Command Prompt, or `ALLOWED_HOSTS=*` to allow any address while testing at home), then open `http://YOUR-PC-IP:8000/` on the phone. In development only `localhost` and `127.0.0.1` are accepted by default.

**If something goes wrong**

| Problem | Fix |
|---|---|
| `No module named 'django'` | The virtual environment is not active, or packages are missing. Activate it, then run `pip install -r requirements.txt`. |
| `pip install` tries to compile Pillow and fails (zlib error) | You are using a non-standard Python (for example the MSYS2/MinGW one). Install Python from python.org and create the environment with `py -m venv venv`. `python -c "import sysconfig; print(sysconfig.get_platform())"` should print `win-amd64`. |
| `Error: That port is already in use` | Another server is running. Stop it, or use another port such as `runserver 8080`. |
| `no such table` or `relation ... does not exist` | Run `python manage.py migrate`. |
| `could not connect to server` | PostgreSQL is not running, or the `DB_*` variables are missing or wrong. |
| The home page has no posters | Run `python manage.py seed`, or add posters at `/manage/posters/`. |
| Poster pictures are missing after cloning | Uploaded images are not stored in git. Upload them again from `/manage/posters/`. |

## Shrinking images uploaded earlier

New uploads are resized automatically. To shrink pictures that were uploaded before that existed:

```bash
python manage.py shrink_images --dry-run    # shows what would change
python manage.py shrink_images              # does it (back up the media/ folder first)
```

## Running the tests

```bash
python manage.py test
```

The suite uses a temporary database, so it never touches your data. It covers the cart, checkout, coupons (including the first-order rule and usage limits), reviews and likes, wishlist, hidden posters, login and staff permissions, pagination and the best-seller deck.

## Useful addresses

| Address | What it is |
|---|---|
| `/` | Home page |
| `/register/`, `/accounts/login/` | Sign up and log in |
| `/cart/`, `/checkout/`, `/orders/` | Shopping flow and order history |
| `/orders/<id>/invoice/` | Printable invoice (the customer who placed it, or staff) |
| `/wishlist/`, `/profile/` | Customer pages |
| `/manage/dashboard/` | Staff panel (staff users only) |
| `/admin/` | Django admin |

## Configuration

All settings come from environment variables.

**Development and production.** The project is safe by default. Development mode turns on by itself only when you start it with `python manage.py ...` (`runserver`, `test`, `migrate` and so on). Anything else, such as gunicorn or another web server, is treated as production. In production the site **refuses to start** unless `SECRET_KEY` (32+ characters) and `ALLOWED_HOSTS` are set. You can override the automatic choice with `DEBUG=1` or `DEBUG=0`.

| Variable | Default | Purpose |
|---|---|---|
| `DEBUG` | on with `manage.py`, off elsewhere | `1` or `0` to force it |
| `SECRET_KEY` | built-in key in development only | Required (32+ random characters) when `DEBUG` is off. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `ALLOWED_HOSTS` | localhost only in development | Required when `DEBUG` is off: comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | none | Comma-separated `https://...` origins, if your host needs them |
| `BEHIND_PROXY` | `0` | Set to `1` when a proxy or load balancer handles HTTPS |
| `ADMIN_PASSWORD` | none | Password for the admin account created by `seed` outside development |
| `DB_ENGINE` | `sqlite` | `postgres` to use PostgreSQL |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | `posterhub`, `postgres`, empty, `127.0.0.1`, `5432` | PostgreSQL connection |
| `EMAIL_BACKEND` | console in development, SMTP otherwise | Set the `EMAIL_*` variables below for real mail |
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
    ├── context.py              # Cart count, real rating and active coupon for the top strip
    ├── tests.py                # Automated tests
    ├── admin.py                # Django admin setup
    ├── migrations/
    ├── management/commands/seed.py
    └── templates/              # All pages, including the staff panel
```

## Going live checklist

1. Run it with a real web server (not `runserver`) and set `SECRET_KEY` and `ALLOWED_HOSTS`. The site will not start without them. With `DEBUG` off it redirects to HTTPS and sends HSTS headers.
2. Use PostgreSQL (`DB_ENGINE=postgres`) and set the `EMAIL_*` variables.
3. Run `python manage.py collectstatic`, then serve the `staticfiles/` folder from your web server (the project does not include WhiteNoise).
4. Serve `media/` (uploaded posters) from your web server or object storage. Django only serves it in debug mode.
5. Do not run `seed` on the live site. If you ever ran it in development, that database has the default `admin / admin123` login: change it with `python manage.py changepassword admin`.

## Known limitations

- Online payment is simulated; there is no real payment gateway yet
- Password-reset pages exist but use Django's default look, and the login page has no "Forgot password?" link
- No rate limiting on login
