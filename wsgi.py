"""Gunicorn entrypoint for Render deployment."""

from app import create_app


app = create_app()
