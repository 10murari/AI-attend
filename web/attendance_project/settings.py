"""
Django settings for Face Recognition Attendance System.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # C:/Final_Project

SECRET_KEY = 'django-insecure-change-this-in-production-xyz123'

DEBUG = True

ALLOWED_HOSTS = ['*']

# ==============================================================
# INSTALLED APPS
# ==============================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'crispy_forms',
    'crispy_bootstrap5',

    # Our apps
    'accounts',
    'academics',
    'attendance',
    'enrollment',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'attendance_project.security.SessionTimeoutMiddleware',
]

ROOT_URLCONF = 'attendance_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'attendance_project.wsgi.application'

# ==============================================================
# DATABASE — Same PostgreSQL you already set up
# ==============================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'attendance_system',
        'USER': 'attendance_admin',
        'PASSWORD': 'root',     # ← CHANGE THIS
        'HOST': 'localhost',
        'PORT': '5433',
    }
}

# ==============================================================
# AUTH
# ==============================================================
AUTH_USER_MODEL = 'accounts.CustomUser'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

# ==============================================================
# STATIC & MEDIA
# ==============================================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ==============================================================
# CRISPY FORMS
# ==============================================================
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# ==============================================================
# FACE RECOGNITION SETTINGS
# ==============================================================
ENROLLMENT_DATA_DIR = PROJECT_ROOT / 'dataset' / 'enrollment'
FACES_DIR = ENROLLMENT_DATA_DIR / 'faces_aligned'
GALLERY_DIR = ENROLLMENT_DATA_DIR / 'gallery'

RECOGNITION_THRESHOLD = 0.45
INSIGHTFACE_MODEL = 'buffalo_l'
DET_SIZE = (640, 640)
DET_THRESH = 0.5

# ==============================================================
# INTERNATIONALIZATION
# ==============================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kathmandu'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================================
# ATTENDANCE NOTIFICATION SETTINGS
# ============================================================

# Request window: hours after session end during which student can request correction
ATTENDANCE_REQUEST_WINDOW = 48  # 48 hours

# Automatically send absence notifications after session ends
AUTO_SEND_ABSENCE_NOTIFICATIONS = True

# Notification retention (days) - after which old notifications are deleted
NOTIFICATION_RETENTION_DAYS = 30

# Pagination
NOTIFICATIONS_PER_PAGE = 20


# Session security
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_SAVE_EVERY_REQUEST = True  # Reset timer on each request
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Password validation (stronger)
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 4}},
]

# CSRF
CSRF_COOKIE_HTTPONLY = False  # Needed for AJAX
CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']

# Security headers (enable in production)
# SECURE_BROWSER_XSS_FILTER = True
# SECURE_CONTENT_TYPE_NOSNIFF = True
# X_FRAME_OPTIONS = 'DENY'

# Login attempt limiting (add django-axes if you want)
# pip install django-axes