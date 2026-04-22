"""Application factory for the assessment tracker."""

import os

from flask import Flask, redirect, render_template, request, url_for
from flask_login import current_user

from config import config_by_name
from .extensions import db, login_manager, migrate
from .services import format_subject_name, get_term_label, get_tracker_mode_label, get_writing_band_label


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application instance."""

    app = Flask(__name__, instance_relative_config=True)

    selected_config = config_name or os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config_by_name.get(selected_config, config_by_name['default']))

    register_extensions(app)
    register_blueprints(app)
    register_request_guards(app)
    register_error_handlers(app)
    register_template_helpers(app)
    register_shell_context(app)

    return app


def register_extensions(app: Flask) -> None:
    """Bind Flask extensions to the application."""

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)


def register_blueprints(app: Flask) -> None:
    """Register all blueprint modules."""

    from .admin import admin_bp
    from .auth import auth_bp
    from .dashboards import dashboards_bp
    from .teacher import teacher_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(admin_bp)


@login_manager.user_loader
def load_user(user_id: str):
    from .models import User

    return User.query.get(int(user_id))


def register_error_handlers(app: Flask) -> None:
    """Register a simple unauthorized flow and common error pages."""

    @login_manager.unauthorized_handler
    def unauthorized():
        next_url = request.path
        return redirect(url_for('auth.login', next=next_url))

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404


def register_request_guards(app: Flask) -> None:
    """Apply application-wide access guards."""

    @app.before_request
    def force_password_change():
        if not current_user.is_authenticated or not getattr(current_user, 'require_password_change', False):
            return None
        if request.endpoint in {'auth.change_password', 'auth.logout', 'static'}:
            return None
        return redirect(url_for('auth.change_password'))





def register_template_helpers(app: Flask) -> None:
    """Expose common formatting helpers to templates."""

    app.jinja_env.globals.update(
        format_subject_name=format_subject_name,
        get_term_label=get_term_label,
        get_writing_band_label=get_writing_band_label,
        get_tracker_mode_label=get_tracker_mode_label,
    )

def register_shell_context(app: Flask) -> None:
    """Add common objects to the Flask shell for quick debugging."""

    from . import models

    @app.shell_context_processor
    def shell_context():
        return {
            'db': db,
            'models': models,
        }
