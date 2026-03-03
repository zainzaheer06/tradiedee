"""
Add clinic-specific fields to Workflow model for Phase 2 implementation
- clinic_feature_type: categorize workflow by clinic feature (appointment_booking, etc.)
- clinic_config: JSON field to store feature-specific configuration

This migration is part of the Clinic Platform Phase 2 implementation.
It can be safely removed if the clinic feature is deleted.
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add clinic fields to workflow table"""
    op.add_column('workflow', sa.Column('clinic_feature_type', sa.String(50), nullable=True))
    op.add_column('workflow', sa.Column('clinic_config', sa.JSON, nullable=True))

    # Create index on clinic_feature_type for faster queries
    op.create_index('ix_workflow_clinic_feature_type', 'workflow', ['clinic_feature_type'])


def downgrade():
    """Remove clinic fields from workflow table"""
    op.drop_index('ix_workflow_clinic_feature_type', table_name='workflow')
    op.drop_column('workflow', 'clinic_config')
    op.drop_column('workflow', 'clinic_feature_type')
