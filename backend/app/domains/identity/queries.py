"""Reusable SQL fragments for role-aware membership queries."""

import uuid

from sqlalchemy import ColumnElement, exists, select

from app.domains.identity.access import CONTRIBUTING_ROLE_KEYS
from app.domains.identity.models import Role, membership_roles


def contributing_membership(
    membership_id: ColumnElement[uuid.UUID], tenant_id: uuid.UUID
) -> ColumnElement[bool]:
    """True when the membership holds a role that may do work (not a Viewer)."""
    return exists(
        select(membership_roles.c.membership_id)
        .join(Role, Role.id == membership_roles.c.role_id)
        .where(
            membership_roles.c.membership_id == membership_id,
            Role.tenant_id == tenant_id,
            Role.key.in_(CONTRIBUTING_ROLE_KEYS),
        )
    )
