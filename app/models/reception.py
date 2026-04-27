"""Reception EYFS tracker model definitions."""

from datetime import datetime, timezone

from app.extensions import db


class ReceptionTrackerEntry(db.Model):
    """Stores a pupil EYFS status per area and tracking point."""

    __tablename__ = 'reception_tracker_entries'
    __table_args__ = (
        db.UniqueConstraint(
            'pupil_id',
            'academic_year',
            'tracking_point',
            'area_key',
            name='uq_reception_tracker_entry_scope',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    tracking_point = db.Column(db.String(40), nullable=False, index=True)
    area_key = db.Column(db.String(60), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default='not_on_track')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='reception_tracker_entries')

    def __repr__(self) -> str:
        return f'<ReceptionTrackerEntry pupil={self.pupil_id} point={self.tracking_point} area={self.area_key}>'
