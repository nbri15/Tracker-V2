"""School and class models."""

from datetime import datetime, timezone

from app.extensions import db


class School(db.Model):
    """Top-level school tenancy boundary for all school data."""

    __tablename__ = 'schools'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False, unique=True)
    slug = db.Column(db.String(140), nullable=False, unique=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    archive_reason = db.Column(db.Text, nullable=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    users = db.relationship('User', back_populates='school', lazy='dynamic')
    classes = db.relationship('SchoolClass', back_populates='school', lazy='dynamic')
    archived_by_user = db.relationship('User')

    def __repr__(self) -> str:
        return f'<School {self.slug}>'


class SchoolClass(db.Model):
    """Represents a school class or year cohort allocation."""

    __tablename__ = 'school_classes'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    year_group = db.Column(db.Integer, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False, index=True)

    school = db.relationship('School', back_populates='classes')
    teacher = db.relationship('User', back_populates='classes')
    pupils = db.relationship('Pupil', back_populates='school_class', lazy='dynamic')

    def __repr__(self) -> str:
        return f'<SchoolClass {self.name}>'
