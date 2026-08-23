"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Enums ───────────────────────────────────────────────────────────────

    member_role = sa.Enum(
        'owner', 'admin', 'editor', 'publisher', 'analyst',
        name='member_role'
    )
    subscription_status = sa.Enum(
        'active', 'trialing', 'past_due', 'cancelled',
        name='subscription_status'
    )
    platform_enum = sa.Enum(
        'instagram', 'facebook', 'tiktok', 'youtube',
        name='platform'
    )
    channel_status = sa.Enum(
        'connected', 'requires_reconnect', 'revoked', 'error',
        name='channel_status'
    )
    media_type = sa.Enum(
        'video', 'image',
        name='media_type'
    )
    asset_status = sa.Enum(
        'uploading', 'processing', 'ready', 'archived', 'error',
        name='asset_status'
    )
    publication_status = sa.Enum(
        'draft', 'queued', 'processing', 'published', 'scheduled',
        'retrying', 'failed', 'needs_reconnect', 'cancelled',
        name='publication_status'
    )
    publication_job_status = sa.Enum(
        'draft', 'queued', 'processing', 'published', 'scheduled',
        'retrying', 'failed', 'needs_reconnect', 'cancelled',
        name='publication_job_status'
    )
    job_error_type = sa.Enum(
        'temporary', 'rate_limit', 'auth', 'invalid_content', 'platform', 'unknown',
        name='job_error_type'
    )

    # ─── users ───────────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(200), nullable=False),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # ─── workspaces ──────────────────────────────────────────────────────────
    op.create_table(
        'workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workspaces_id'), 'workspaces', ['id'], unique=False)
    op.create_index(op.f('ix_workspaces_slug'), 'workspaces', ['slug'], unique=True)

    # ─── memberships ─────────────────────────────────────────────────────────
    op.create_table(
        'memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', member_role, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('invited_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_memberships_workspace_id'), 'memberships', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'], unique=False)

    # ─── subscriptions ───────────────────────────────────────────────────────
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('plan_name', sa.String(50), nullable=False),
        sa.Column('status', subscription_status, nullable=False, server_default='trialing'),
        sa.Column('plan_config', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('external_subscription_id', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id'),
    )

    # ─── social_channels ─────────────────────────────────────────────────────
    op.create_table(
        'social_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('platform', platform_enum, nullable=False),
        sa.Column('alias', sa.String(200), nullable=False),
        sa.Column('remote_id', sa.String(200), nullable=False),
        sa.Column('remote_name', sa.String(200), nullable=True),
        sa.Column('remote_username', sa.String(200), nullable=True),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('status', channel_status, nullable=False, server_default='connected'),
        sa.Column('capabilities', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('platform_meta', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('connected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_social_channels_id'), 'social_channels', ['id'], unique=False)
    op.create_index(op.f('ix_social_channels_workspace_id'), 'social_channels', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_social_channels_platform'), 'social_channels', ['platform'], unique=False)

    # ─── oauth_credentials ───────────────────────────────────────────────────
    op.create_table(
        'oauth_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('access_token_enc', sa.String(2000), nullable=False),
        sa.Column('refresh_token_enc', sa.String(2000), nullable=True),
        sa.Column('token_type', sa.String(50), nullable=True, server_default='Bearer'),
        sa.Column('scope', sa.String(500), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['social_channels.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel_id'),
    )

    # ─── channel_groups ──────────────────────────────────────────────────────
    op.create_table(
        'channel_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_channel_groups_workspace_id'), 'channel_groups', ['workspace_id'], unique=False)

    # ─── group_channels (M:N) ────────────────────────────────────────────────
    op.create_table(
        'group_channels',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['channel_groups.id'], ),
        sa.ForeignKeyConstraint(['channel_id'], ['social_channels.id'], ),
        sa.PrimaryKeyConstraint('group_id', 'channel_id'),
    )

    # ─── media_assets ────────────────────────────────────────────────────────
    op.create_table(
        'media_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('media_type', media_type, nullable=False),
        sa.Column('status', asset_status, nullable=False, server_default='uploading'),
        sa.Column('storage_key', sa.String(1000), nullable=False),
        sa.Column('storage_bucket', sa.String(200), nullable=False),
        sa.Column('public_url', sa.String(1000), nullable=True),
        sa.Column('thumbnail_url', sa.String(1000), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('fps', sa.Float(), nullable=True),
        sa.Column('codec', sa.String(50), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('aspect_ratio', sa.String(20), nullable=True),
        sa.Column('tags', sa.String(500), nullable=True),
        sa.Column('folder', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_media_assets_id'), 'media_assets', ['id'], unique=False)
    op.create_index(op.f('ix_media_assets_workspace_id'), 'media_assets', ['workspace_id'], unique=False)

    # ─── publications ─────────────────────────────────────────────────────────
    op.create_table(
        'publications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('media_asset_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('captions', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('platform_settings', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', publication_status, nullable=False, server_default='draft'),
        sa.Column('target_channel_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('total_jobs', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('jobs_published', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('jobs_failed', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('jobs_pending', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.ForeignKeyConstraint(['media_asset_id'], ['media_assets.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_publications_id'), 'publications', ['id'], unique=False)
    op.create_index(op.f('ix_publications_workspace_id'), 'publications', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_publications_status'), 'publications', ['status'], unique=False)

    # ─── publication_jobs ────────────────────────────────────────────────────
    op.create_table(
        'publication_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('publication_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('job_idempotency_key', sa.String(200), nullable=False),
        sa.Column('celery_task_id', sa.String(200), nullable=True),
        sa.Column('remote_publication_id', sa.String(200), nullable=True),
        sa.Column('remote_url', sa.String(1000), nullable=True),
        sa.Column('status', publication_job_status, nullable=False, server_default='queued'),
        sa.Column('attempt_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=True, server_default='5'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('error_type', job_error_type, nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['publications.id'], ),
        sa.ForeignKeyConstraint(['channel_id'], ['social_channels.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_idempotency_key'),
    )
    op.create_index(op.f('ix_publication_jobs_id'), 'publication_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_publication_jobs_publication_id'), 'publication_jobs', ['publication_id'], unique=False)
    op.create_index(op.f('ix_publication_jobs_channel_id'), 'publication_jobs', ['channel_id'], unique=False)
    op.create_index(op.f('ix_publication_jobs_celery_task_id'), 'publication_jobs', ['celery_task_id'], unique=False)
    op.create_index(op.f('ix_publication_jobs_status'), 'publication_jobs', ['status'], unique=False)

    # ─── analytics_snapshots ─────────────────────────────────────────────────
    op.create_table(
        'analytics_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('views', sa.Integer(), nullable=True),
        sa.Column('likes', sa.Integer(), nullable=True),
        sa.Column('comments', sa.Integer(), nullable=True),
        sa.Column('shares', sa.Integer(), nullable=True),
        sa.Column('followers_gained', sa.Integer(), nullable=True),
        sa.Column('reach', sa.Integer(), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['publication_jobs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_analytics_snapshots_job_id'), 'analytics_snapshots', ['job_id'], unique=False)

    # ─── audit_logs ──────────────────────────────────────────────────────────
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_logs_workspace_id'), 'audit_logs', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('analytics_snapshots')
    op.drop_table('publication_jobs')
    op.drop_table('publications')
    op.drop_table('media_assets')
    op.drop_table('group_channels')
    op.drop_table('channel_groups')
    op.drop_table('oauth_credentials')
    op.drop_table('social_channels')
    op.drop_table('subscriptions')
    op.drop_table('memberships')
    op.drop_table('workspaces')
    op.drop_table('users')

    # Drop enums
    sa.Enum(name='job_error_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='publication_job_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='publication_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='asset_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='media_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='channel_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='platform').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='subscription_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='member_role').drop(op.get_bind(), checkfirst=True)
