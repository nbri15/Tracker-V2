"""School class model."""

from app.extensions import db


class SchoolClass(db.Model):
    """Represents a school class or year cohort allocation."""

    __tablename__ = 'school_classes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    year_group = db.Column(db.Integer, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    teacher = db.relationship('User', back_populates='classes')
    pupils = db.relationship('Pupil', back_populates='school_class', lazy='dynamic')

    def __repr__(self) -> str:
        return f'<SchoolClass {self.name}>'
