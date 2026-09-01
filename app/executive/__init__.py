from flask import Blueprint

executive_bp = Blueprint('executive', __name__, url_prefix='/exec')

from . import routes  # noqa: E402,F401
