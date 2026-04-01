"""add users and schedules

Revision ID: a2d5f33f3ef3
Revises: 
Create Date: 2026-04-01 16:26:32.687005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2d5f33f3ef3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedules")
    op.execute("DROP TABLE IF EXISTS users")

    op.create_table('schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('polsl_sid', sa.String(), nullable=True),
    sa.Column('semester', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_schedules_id'), 'schedules', ['id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('telegram_chat_id', sa.String(), nullable=True),
    sa.Column('whatsapp_number', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('schedule_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['schedule_id'], ['schedules.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('telegram_chat_id'),
    sa.UniqueConstraint('whatsapp_number')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    op.add_column('events', sa.Column('schedule_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('events') as batch_op:
        batch_op.create_foreign_key('fk_events_schedule', 'schedules', ['schedule_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('events') as batch_op:
        batch_op.drop_constraint('fk_events_schedule', type_='foreignkey')
        batch_op.drop_column('schedule_id')

    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_schedules_id'), table_name='schedules')
    op.drop_table('schedules')