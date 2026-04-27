"""User account model definitions."""

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    """Application user with either admin or teacher access."""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    legacy_is_admin = db.Column('is_admin', db.Boolean, nullable=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)
    role = db.Column(db.String(20), nullable=False, default='teacher')
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False, index=True)
    require_password_change = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    school = db.relationship('School', back_populates='users')
    classes = db.relationship('SchoolClass', back_populates='teacher', lazy='dynamic')

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        if self.legacy_is_admin is not None:
            return bool(self.legacy_is_admin)
        return self.role in {'school_admin', 'executive_admin', 'admin'}

    @property
    def is_executive_admin(self) -> bool:
        return self.role == 'executive_admin'

    @property
    def is_school_admin(self) -> bool:
        return self.role == 'school_admin' or (self.is_admin and self.role != 'executive_admin')

    @property
    def is_teacher(self) -> bool:
        return self.role == 'teacher'

    @property
    def can_manage_school(self) -> bool:
        return self.is_executive_admin or self.is_school_admin

    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self) -> str:
        return f'<User {self.username}>'
