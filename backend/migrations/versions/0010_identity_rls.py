"""Apply tenant and token-scoped RLS to identity tables."""
from alembic import op
import sqlalchemy as sa

revision = "0010_identity_rls"
down_revision = "0009_finished_product_quality"
branch_labels = None
depends_on = None


ORG = "NULLIF(current_setting('app.current_organization_id', true), '')::bigint"


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute('ALTER TABLE organizations ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE organizations FORCE ROW LEVEL SECURITY')
    op.execute(sa.text(
        f"""CREATE POLICY organizations_scoped_access ON organizations
            FOR SELECT USING (
                id = {ORG}
                OR current_setting('app.organization_provisioning', true) = 'on'
                OR code = NULLIF(current_setting('app.supplier_organization_code', true), '')
                OR current_setting('app.system_job', true) = 'maintenance-reminders'
            )"""
    ))
    op.execute(
        """CREATE POLICY organizations_provision_insert ON organizations
           FOR INSERT WITH CHECK (
               current_setting('app.organization_provisioning', true) = 'on'
           )"""
    )

    op.execute('ALTER TABLE users ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE users FORCE ROW LEVEL SECURITY')
    op.execute(sa.text(
        f"""CREATE POLICY users_scoped_access ON users
            FOR SELECT USING (
                organization_id = {ORG}
                OR lower(email) = lower(NULLIF(current_setting('app.auth_email', true), ''))
                OR id = NULLIF(current_setting('app.auth_user_id', true), '')::bigint
            )"""
    ))
    op.execute(sa.text(
        f"""CREATE POLICY users_tenant_insert ON users
            FOR INSERT WITH CHECK (organization_id = {ORG})"""
    ))
    op.execute(sa.text(
        f"""CREATE POLICY users_scoped_update ON users
            FOR UPDATE USING (
                organization_id = {ORG}
                OR id = NULLIF(current_setting('app.auth_user_id', true), '')::bigint
            )
            WITH CHECK (
                organization_id = {ORG}
                OR id = NULLIF(current_setting('app.auth_user_id', true), '')::bigint
            )"""
    ))

    op.execute('ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY')
    op.execute(sa.text(
        f"""CREATE POLICY refresh_tokens_scoped_access ON refresh_tokens
            FOR SELECT USING (
                token_hash = NULLIF(current_setting('app.auth_refresh_token_hash', true), '')
                OR user_id IN (SELECT id FROM users WHERE organization_id = {ORG})
            )"""
    ))
    op.execute(sa.text(
        f"""CREATE POLICY refresh_tokens_tenant_insert ON refresh_tokens
            FOR INSERT WITH CHECK (
                user_id IN (SELECT id FROM users WHERE organization_id = {ORG})
            )"""
    ))
    op.execute(sa.text(
        f"""CREATE POLICY refresh_tokens_scoped_update ON refresh_tokens
            FOR UPDATE USING (
                user_id IN (SELECT id FROM users WHERE organization_id = {ORG})
                OR token_hash = NULLIF(current_setting('app.auth_refresh_token_hash', true), '')
            )
            WITH CHECK (
                user_id IN (SELECT id FROM users WHERE organization_id = {ORG})
                OR token_hash = NULLIF(current_setting('app.auth_refresh_token_hash', true), '')
            )"""
    ))

    op.execute('ALTER TABLE auth_action_tokens ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE auth_action_tokens FORCE ROW LEVEL SECURITY')
    op.execute(sa.text(
        f"""CREATE POLICY auth_action_tokens_scoped_access ON auth_action_tokens
            FOR SELECT USING (
                organization_id = {ORG}
                OR token_hash = NULLIF(current_setting('app.auth_action_token_hash', true), '')
            )"""
    ))
    op.execute(sa.text(
        f"""CREATE POLICY auth_action_tokens_tenant_insert ON auth_action_tokens
            FOR INSERT WITH CHECK (organization_id = {ORG})"""
    ))
    op.execute(sa.text(
        f"""CREATE POLICY auth_action_tokens_scoped_update ON auth_action_tokens
            FOR UPDATE USING (
                organization_id = {ORG}
                OR token_hash = NULLIF(current_setting('app.auth_action_token_hash', true), '')
            )
            WITH CHECK (
                organization_id = {ORG}
                OR token_hash = NULLIF(current_setting('app.auth_action_token_hash', true), '')
            )"""
    ))


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, policy in (
        ("auth_action_tokens", "auth_action_tokens_scoped_update"),
        ("auth_action_tokens", "auth_action_tokens_tenant_insert"),
        ("auth_action_tokens", "auth_action_tokens_scoped_access"),
        ("refresh_tokens", "refresh_tokens_scoped_update"),
        ("refresh_tokens", "refresh_tokens_tenant_insert"),
        ("refresh_tokens", "refresh_tokens_scoped_access"),
        ("users", "users_scoped_update"),
        ("users", "users_tenant_insert"),
        ("users", "users_scoped_access"),
        ("organizations", "organizations_provision_insert"),
        ("organizations", "organizations_scoped_access"),
    ):
        op.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
    for table in ("auth_action_tokens", "refresh_tokens", "users", "organizations"):
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
