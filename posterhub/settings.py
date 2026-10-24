import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default):
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


# ── Safe by default ───────────────────────────────────────────────────────────
# Development mode switches on by itself only when you start the project with
# "python manage.py ..." (runserver, test, migrate, ...). Anything else, such as
# gunicorn or any other web server, is treated as production unless DEBUG=1 is
# set on purpose. In production the site refuses to start without a real
# SECRET_KEY and ALLOWED_HOSTS.
_DEV_SECRET_KEY = "dev-only-insecure-key-never-use-in-production"
DEBUG = _env_bool("DEBUG", default=Path(sys.argv[0]).name == "manage.py")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")   # in development, empty means localhost only
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")

if DEBUG:
    SECRET_KEY = SECRET_KEY or _DEV_SECRET_KEY
else:
    if len(SECRET_KEY) < 32 or SECRET_KEY.startswith(("dev-only", "django-insecure")):
        raise ImproperlyConfigured(
            "SECRET_KEY must be set to a long random value (32+ characters) when DEBUG is off. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must list your site's hostnames when DEBUG is off, "
            "for example ALLOWED_HOSTS=shop.example.com"
        )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "shop",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "posterhub.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shop.context.cart_count",
                "shop.context.site_promos",
            ]
        },
    }
]

WSGI_APPLICATION = "posterhub.wsgi.application"

# ── Database ──────────────────────────────────────────────────────────────────
# Set DB_ENGINE=postgres and the DB_* env vars to use PostgreSQL.
# All connection settings default to typical local dev values.
_db_engine = os.environ.get("DB_ENGINE", "sqlite")

if _db_engine == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "posterhub"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            # Keep connections alive to avoid reconnect overhead (60s in prod).
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {
                # Use statement-level timeout to avoid runaway queries (30 s).
                "options": "-c statement_timeout=30000",
                # Enable server-side cursors for large querysets.
                "server_side_cursors": True,
                # Require SSL in production (PGSSLMODE env var).
                **(
                    {"sslmode": os.environ["PGSSLMODE"]}
                    if os.environ.get("PGSSLMODE")
                    else {}
                ),
            },
            "TEST": {
                "NAME": os.environ.get("DB_TEST_NAME", "test_posterhub"),
            },
        }
    }
elif _db_engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DB_NAME", "posterhub"),
            "USER": os.environ.get("DB_USER", "root"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    # SQLite fallback for local development / CI
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ── Static & media ────────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── Email ─────────────────────────────────────────────────────────────────────
# Emails print to the terminal in development and go through SMTP otherwise.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "0") == "1"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@posterhub.com")

# ── Sessions ──────────────────────────────────────────────────────────────────
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 weeks
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# ── Security (tighten in production via env vars) ─────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.environ.get("HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    if _env_bool("BEHIND_PROXY", False):   # set when a proxy/load balancer terminates HTTPS
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ── Pagination defaults ───────────────────────────────────────────────────────
ADMIN_PAGE_SIZE = int(os.environ.get("ADMIN_PAGE_SIZE", "25"))
