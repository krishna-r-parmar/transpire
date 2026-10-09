"""Import persistence models once so Alembic can inspect complete metadata."""

from app.domains.audit import models as audit_models  # noqa: F401
from app.domains.communications import models as communications_models  # noqa: F401
from app.domains.configuration import models as configuration_models  # noqa: F401
from app.domains.ideas import models as idea_models  # noqa: F401
from app.domains.identity import models as identity_models  # noqa: F401
from app.domains.projects import models as project_models  # noqa: F401
from app.domains.tenants import models as tenant_models  # noqa: F401
