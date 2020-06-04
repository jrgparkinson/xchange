"""
Django settings for xchange project.

Generated by 'django-admin startproject' using Django 3.0.6.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "ucolgyxgu7!gp-@9ya575-+(shy^qqhsqb2no-c8$d0-=vq0x7"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["http://127.0.0.1/", "jrgparkinson.com"]


# Application definition

INSTALLED_APPS = [
    "app.apps.AppConfig",
    "django.contrib.admin",
    # 'django.contrib.admin.apps.SimpleAdminConfig',
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'import_export',
    'background_task',
    'admin_reorder',
    # 'django.contrib.sites',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    #  'admin_reorder.middleware.ModelAdminReorder',
]

ROOT_URLCONF = "xchange.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "xchange.wsgi.application"


# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]


# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

STATIC_ROOT = "static"

LOGIN_REDIRECT_URL = "/profile/"

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"  # During development only
)
# EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = os.path.join(BASE_DIR, "sent_emails")


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

ADMIN_REORDER = (
    {'app': 'app', 'label': 'Users',
        'models': (
            'app.Investor',
            'app.Bank',
            'app.Notification',
            'app.LoanOffer',
            'app.Loan',
            'app.Debt',
        )
   },
      {'app': 'app', 'label': 'Trading',
        'models': (
            'app.Trade',
        )
   },
   {'app': 'app', 'label': 'Assets',
        'models': (
            'app.Athlete',
            'app.Asset',
            'app.Share',
            'app.Future',
            'app.Option',
            'app.Swap',
            'app.Contract',
        )
   },
      {'app': 'app', 'label': 'History',
        'models': (
            'app.ShareIndexValue',
            'app.TransactionHistory',
            'app.ContractHistory',
            'app.Swap',
        )
   },
   {'app': 'app', 'label': 'Events',
        'models': (
            'app.Season',
            'app.Event',
            'app.Race',
            'app.Result',
        )
   },
      {'app': 'app', 'label': 'Auctions',
        'models': (
            'app.Lot',
            'app.Bid',
            'app.Auction',
        )
   },
    {'app': 'background', 'label': 'Tasks',
        'models': (
            'background.Task',
            'background.CompletedTask',
        )
   },
)

# Set > 0 to determine number of seconds after a future trade is done that the
# future is settled (for testing purposes)
TESTING_FUTURES_TIMING = 0