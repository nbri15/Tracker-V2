from flask import Blueprint

fundamentals_bp = Blueprint('fundamentals', __name__, url_prefix='/fundamentals')



@fundamentals_bp.before_request
def hide_when_switched_off():
    """While the feature is off every Maths Fundamentals page, including pupil join links, shows 'not found'."""
    from flask import abort, current_app
    if not current_app.config.get('FUNDAMENTALS_ENABLED', False):
        abort(404)


from . import routes  # noqa: E402,F401
