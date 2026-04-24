"""Pupil directory and profile routes."""

from flask import Blueprint

pupils_bp = Blueprint('pupils', __name__, url_prefix='/pupils')

from . import routes  # noqa: E402,F401
