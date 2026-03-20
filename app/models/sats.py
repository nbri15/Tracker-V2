"""Year 6 SATs data models and tracker configuration."""

from datetime import datetime, timezone

from app.extensions import db


class TrackerModeSetting(db.Model):
    """Stores whether a year group uses the usual tracker or SATs tracker."""

    __tablename__ = 'tracker_mode_settings'
    __table_args__ = (
        db.UniqueConstraint('year_group', name='uq_tracker_mode_year_group'),
    )

    id = db.Column(db.Integer, primary_key=True)
    year_group = db.Column(db.Integer, nullable=False, index=True)
    tracker_mode = db.Column(db.String(20), nullable=False, default='normal')
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f'<TrackerModeSetting Y{self.year_group} {self.tracker_mode}>'


class SatsColumnSetting(db.Model):
    """Configurable Year 6 SATs assessment columns."""

    __tablename__ = 'sats_column_settings'
    __table_args__ = (
        db.Index('ix_sats_column_year_order', 'year_group', 'display_order'),
    )

    id = db.Column(db.Integer, primary_key=True)
    year_group = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(40), nullable=False, index=True)
    max_marks = db.Column(db.Integer, nullable=False, default=40)
    pass_percentage = db.Column(db.Float, nullable=False, default=60.0)
    display_order = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    results = db.relationship('SatsColumnResult', back_populates='column', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self) -> str:
        return f'<SatsColumnSetting Y{self.year_group} {self.name}>'


class SatsColumnResult(db.Model):
    """Per-pupil score for one flexible SATs column."""

    __tablename__ = 'sats_column_results'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'column_id', 'academic_year', name='uq_sats_column_result_scope'),
        db.Index('ix_sats_column_result_lookup', 'academic_year', 'column_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey('sats_column_settings.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    raw_score = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='sats_column_results')
    column = db.relationship('SatsColumnSetting', back_populates='results')

    def __repr__(self) -> str:
        return f'<SatsColumnResult column={self.column_id} pupil={self.pupil_id}>'


class SatsResult(db.Model):
    """Legacy SATs practice or assessment point outcomes for Year 6 pupils."""

    __tablename__ = 'sats_results'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'subject', 'assessment_point', 'academic_year', name='uq_sats_result_scope'),
        db.Index('ix_sats_result_lookup', 'academic_year', 'subject', 'assessment_point'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False)
    assessment_point = db.Column(db.Integer, nullable=False)
    raw_score = db.Column(db.Integer, nullable=True)
    scaled_score = db.Column(db.Integer, nullable=True)
    is_most_recent = db.Column(db.Boolean, nullable=False, default=False)
    academic_year = db.Column(db.String(20), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='sats_results')

    def __repr__(self) -> str:
        return f'<SatsResult {self.subject} AP{self.assessment_point}>'


class SatsWritingResult(db.Model):
    """Legacy Year 6 writing judgements for each assessment point."""

    __tablename__ = 'sats_writing_results'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'assessment_point', 'academic_year', name='uq_sats_writing_scope'),
        db.Index('ix_sats_writing_lookup', 'academic_year', 'assessment_point'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    assessment_point = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    band = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='sats_writing_results')

    def __repr__(self) -> str:
        return f'<SatsWritingResult AP{self.assessment_point}>'
