# PosterHub (Django)
## Run locally
    python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    python manage.py makemigrations shop
    python manage.py migrate
    python manage.py seed          # sample posters + admin / admin123
    python manage.py runserver     # http://127.0.0.1:8000  (admin: /admin/)
## MySQL
Install mysqlclient, create a database, then set env vars before migrate:
DB_ENGINE=mysql DB_NAME=posterhub DB_USER=root DB_PASSWORD=... DB_HOST=127.0.0.1
## Not done yet (SRS items for the next pass)
Payment gateway, password-reset emails, offers/discounts, admin sales charts, product image upload UX, tests, production hardening (HTTPS, ALLOWED_HOSTS, SECRET_KEY).
