from flask import send_from_directory

from . import legal_bp


@legal_bp.route('/privacy')
def privacy():
    return send_from_directory('static/docs', 'class_compass_privacy_policy.pdf')


@legal_bp.route('/terms')
def terms():
    return send_from_directory('static/docs', 'class_compass_terms_of_use.pdf')
