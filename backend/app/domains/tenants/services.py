from app.domains.tenants.models import TenantStatus


def tenant_can_authenticate(status: TenantStatus) -> bool:
    """Central tenant lifecycle policy used by identity use cases."""

    return status is TenantStatus.ACTIVE
