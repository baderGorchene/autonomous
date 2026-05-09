from alembic import op
import sqlalchemy as sa

revision = 'initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('owners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('business_name', sa.String(), nullable=True),
        sa.Column('slug', sa.String(), nullable=True),
        sa.Column('services_json', sa.JSON(), nullable=True),
        sa.Column('availability_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_owners_email'), 'owners', ['email'], unique=True)
    op.create_index(op.f('ix_owners_id'), 'owners', ['id'], unique=False)
    op.create_index(op.f('ix_owners_slug'), 'owners', ['slug'], unique=True)
    op.create_table('bookings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('customer_name', sa.String(), nullable=True),
        sa.Column('customer_email', sa.String(), nullable=True),
        sa.Column('customer_phone', sa.String(), nullable=True),
        sa.Column('service', sa.String(), nullable=True),
        sa.Column('datetime', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bookings_id'), 'bookings', ['id'], unique=False)
    op.create_table('settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('timezone', sa.String(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_settings_id'), 'settings', ['id'], unique=False)

def downgrade():
    op.drop_table('settings')
    op.drop_table('bookings')
    op.drop_table('owners')