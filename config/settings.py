"""
Django settings — control + publishing planes in one project (architecture.md §5).

All secrets/config come from .env via django-environ (12-factor). Host routing
between the two planes is done per-request by apps.sites.middleware
.HostRouterMiddleware, keyed on BASE_DOMAIN / APP_HOST below.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

# --- Host routing (architecture.md §6) ---------------------------------------
# BASE_DOMAIN: wildcard base for published sites ({subdomain}.BASE_DOMAIN).
# APP_HOST: exact host of the control plane (editor/admin).
# Both may carry a :port in dev; hostname-only forms are derived for matching.
BASE_DOMAIN = env("BASE_DOMAIN", default="localhost:8000")
APP_HOST = env("APP_HOST", default=f"app.{BASE_DOMAIN}")
BASE_DOMAIN_NAME = BASE_DOMAIN.rsplit(":", 1)[0]
APP_HOST_NAME = APP_HOST.rsplit(":", 1)[0]

ALLOWED_HOSTS = [APP_HOST_NAME, BASE_DOMAIN_NAME, f".{BASE_DOMAIN_NAME}"]

# --- Apps ---------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_q",
    "apps.accounts",
    "apps.sites",
    "apps.editor",
    "apps.publishing",
    "apps.common",
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

# Default urlconf is the control plane; HostRouterMiddleware overrides
# request.urlconf per request.
ROOT_URLCONF = "config.urls_control"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database -----------------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth ---------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Sessions / cookies (architecture.md §12) ----------------------------------
# Only the control plane uses sessions. SESSION_COOKIE_DOMAIN stays None so the
# cookie is HOST-ONLY on APP_HOST — strictly tighter than an explicit Domain
# attribute (which would also match subdomains of the app host) and never
# anywhere near Domain=.BASE_DOMAIN.
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_DOMAIN = None
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = [
    f"http://{APP_HOST}" if DEBUG else f"https://{APP_HOST}",
]

# --- Django-Q2 (ORM broker — no Redis in v1, architecture.md §14) ---------------

Q_CLUSTER = {
    "name": "industry_rockstar",
    "orm": "default",  # use the Postgres connection as the broker
    "workers": 2,
    "timeout": 300,  # a single import/rehost job may fetch many assets
    "retry": 360,  # must exceed timeout
    "max_attempts": 3,
    "label": "Background jobs",
}

# --- I18N / static -------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
