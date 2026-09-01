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
