from flask import Flask

from app.extensions import csrf
from app.utils import safe_redirect_target


def test_safe_redirect_rejects_external_targets():
    assert safe_redirect_target('https://evil.example/phish', '/dashboard') == '/dashboard'
    assert safe_redirect_target('//evil.example/phish', '/dashboard') == '/dashboard'
    assert safe_redirect_target('/admin/pupils', '/dashboard') == '/admin/pupils'


def test_csrf_rejects_unprotected_post():
    app = Flask(__name__)
    app.config.update(SECRET_KEY='test', TESTING=True)
    csrf.init_app(app)

    @app.post('/mutate')
    def mutate():
        return 'changed'

    response = app.test_client().post('/mutate')
    assert response.status_code == 400


def test_security_headers_are_compatible_with_current_frontend():
    from app import register_request_guards
    from app.extensions import db, login_manager

    app = Flask(__name__)
    app.config.update(SECRET_KEY='test', TESTING=True, ENV='production', SQLALCHEMY_DATABASE_URI='sqlite://')
    db.init_app(app)
    login_manager.init_app(app)
    register_request_guards(app)

    @app.get('/')
    def index():
        return 'ok'

    response = app.test_client().get('/')
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
    assert response.headers['Strict-Transport-Security'].startswith('max-age=')
