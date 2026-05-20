import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
INSTANCE_DIR.mkdir(exist_ok=True)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _ensure_sslmode_require(db_uri: str) -> str:
    if not db_uri.startswith(('postgresql://', 'postgres://')):
        return db_uri
    parts = urlsplit(db_uri)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    if any(key == 'sslmode' for key, _ in query_pairs):
        return db_uri
    query_pairs.append(('sslmode', 'require'))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_pairs), parts.fragment))


def _normalize_database_uri(raw_uri: str | None) -> str:
    """Normalize DB URLs so SQLAlchemy works across local and Render environments."""

    if not raw_uri:
        return f"sqlite:///{INSTANCE_DIR / 'assessment_tracker.db'}"
    # Render/Heroku style URLs may use postgres:// which SQLAlchemy 1.4+/2 expects as postgresql://
    if raw_uri.startswith('postgres://'):
        raw_uri = raw_uri.replace('postgres://', 'postgresql://', 1)
    return _ensure_sslmode_require(raw_uri)


class Config:
    """Base configuration shared across all environments."""

    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(os.environ.get('DATABASE_URL'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_timeout': 30,
        'max_overflow': 10,
    }
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    # Default hardening is safe for both environments; Production overrides as needed.
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    DEMO_MODE = _env_flag('DEMO_MODE', default=False)


class DevelopmentConfig(Config):
    """Development-friendly defaults for local setup."""

    DEBUG = True
    ENV = 'development'
    ALLOW_DEV_BOOTSTRAP = True


class ProductionConfig(Config):
    """Production configuration for Render deployment."""

    DEBUG = False
    ENV = 'production'
    ALLOW_DEV_BOOTSTRAP = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
