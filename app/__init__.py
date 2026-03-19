"""Application factory for the assessment tracker."""

import os

from flask import Flask, redirect, render_template, request, url_for

from config import config_by_name
from .extensions import db, login_manager, migrate


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application instance."""

    app = Flask(__name__, instance_relative_config=True)

    selected_config = config_name or os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config_by_name.get(selected_config, config_by_name['default']))

    register_extensions(app)
    register_blueprints(app)
    register_error_handlers(app)
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



def register_shell_context(app: Flask) -> None:
    """Add common objects to the Flask shell for quick debugging."""

    from . import models

    @app.shell_context_processor
    def shell_context():
        return {
            'db': db,
            'models': models,
        }
