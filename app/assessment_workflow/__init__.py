from flask import Blueprint
assessment_bp = Blueprint('assessment_workflow', __name__)
from . import routes
