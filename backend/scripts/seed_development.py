import asyncio

from sqlalchemy import insert, select

from app.core.config import get_settings
from app.core.database import session_factory
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.configuration.controllers import (
    create_default_master_data,
    create_default_workflow,
)
from app.domains.configuration.models import ConfigurationItem, WorkflowDefinition
from app.domains.ideas.models import IdeaBankPolicy
from app.domains.ideas.services import create_default_idea_bank_policy
from app.domains.identity.models import (
    Membership,
    MembershipStatus,
    Role,
    User,
    membership_roles,
)
from app.domains.identity.services import hash_password
from app.domains.tenants.models import Tenant, TenantStatus


async def seed() -> None:
    settings = get_settings()
    if settings.environment.casefold() == "production":
        raise RuntimeError("Development seeding is disabled in production")

    password = settings.development_admin_password.get_secret_value()
    if len(password) < 12:
        raise RuntimeError("DEV_ADMIN_PASSWORD must contain at least 12 characters")

    async with session_factory() as session, session.begin():
        tenant = await session.scalar(
            select(Tenant).where(Tenant.slug == settings.development_tenant_slug)
        )
        if tenant is None:
            tenant = Tenant(
                slug=settings.development_tenant_slug,
                name=settings.development_tenant_name,
                status=TenantStatus.ACTIVE,
                settings={},
                branding={},
            )
            session.add(tenant)
            await session.flush()
        else:
            tenant.name = settings.development_tenant_name
            tenant.status = TenantStatus.ACTIVE

        await apply_tenant_to_transaction(session, tenant.id)

        workflow_exists = await session.scalar(
            select(WorkflowDefinition.id).where(
                WorkflowDefinition.tenant_id == tenant.id,
                WorkflowDefinition.key == "idea_approval",
            )
        )
        if workflow_exists is None:
            create_default_workflow(session, tenant.id)

        category_exists = await session.scalar(
            select(ConfigurationItem.id).where(
                ConfigurationItem.tenant_id == tenant.id,
                ConfigurationItem.kind == "category",
            )
        )
        if category_exists is None:
            create_default_master_data(session, tenant.id)

        policy_exists = await session.scalar(
            select(IdeaBankPolicy.id).where(IdeaBankPolicy.tenant_id == tenant.id)
        )
        if policy_exists is None:
            create_default_idea_bank_policy(session, tenant.id)

        email = str(settings.development_admin_email).casefold()
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                display_name=settings.development_admin_name,
                password_hash=hash_password(password),
                is_platform_admin=True,
            )
            session.add(user)
            await session.flush()
        else:
            user.display_name = settings.development_admin_name
            user.password_hash = hash_password(password)
            user.is_platform_admin = True

        membership = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant.id,
                Membership.user_id == user.id,
            )
        )
        if membership is None:
            membership = Membership(
                tenant_id=tenant.id,
                user_id=user.id,
                status=MembershipStatus.ACTIVE,
            )
            session.add(membership)
            await session.flush()
        else:
            membership.status = MembershipStatus.ACTIVE
            membership.failed_sign_in_attempts = 0
            membership.locked_until = None

        role = await session.scalar(
            select(Role).where(Role.tenant_id == tenant.id, Role.key == "tenant_admin")
        )
        if role is None:
            role = Role(
                tenant_id=tenant.id,
                key="tenant_admin",
                name="Tenant Administrator",
                permissions=[
                    "idea.create",
                    "idea.view",
                    "tenant.people.manage",
                    "tenant.settings.manage",
                ],
                is_system=True,
            )
            session.add(role)
            await session.flush()

        assignment_exists = await session.scalar(
            select(membership_roles.c.membership_id).where(
                membership_roles.c.membership_id == membership.id,
                membership_roles.c.role_id == role.id,
            )
        )
        if assignment_exists is None:
            await session.execute(
                insert(membership_roles).values(
                    membership_id=membership.id,
                    role_id=role.id,
                )
            )

    print("Development tenant and administrator are ready.")
    print(f"Workspace URL: {settings.public_app_url.rstrip('/')}/t/{tenant.slug}/sign-in")
    print(f"Administrator email: {settings.development_admin_email}")


if __name__ == "__main__":
    asyncio.run(seed())
