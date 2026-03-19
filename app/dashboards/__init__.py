from flask import Blueprint


dashboards_bp = Blueprint('dashboards', __name__)

from . import routes  # noqa: E402,F401
