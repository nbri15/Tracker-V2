from flask import Blueprint

maths_fundamentals_bp = Blueprint('maths_fundamentals', __name__, url_prefix='/maths-fundamentals')

from . import routes  # noqa: E402,F401
