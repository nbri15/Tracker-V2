from flask import Blueprint


legal_bp = Blueprint('legal', __name__)

from . import routes  # noqa: E402,F401
