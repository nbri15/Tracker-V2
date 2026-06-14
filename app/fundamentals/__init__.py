from flask import Blueprint

fundamentals_bp = Blueprint('fundamentals', __name__, url_prefix='/fundamentals')

from . import routes  # noqa: E402,F401
