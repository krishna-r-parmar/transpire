import uuid

import pytest

from app.core.tenant_context import (
    TenantContext,
    require_tenant_context,
    reset_tenant_context,
    set_tenant_context,
)


def test_tenant_context_must_be_explicit() -> None:
    with pytest.raises(RuntimeError, match="Tenant context is required"):
        require_tenant_context()


def test_tenant_context_can_be_scoped_and_reset() -> None:
    context = TenantContext(tenant_id=uuid.uuid4(), slug="example-industries")
    token = set_tenant_context(context)

    assert require_tenant_context() == context

    reset_tenant_context(token)
