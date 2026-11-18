"""Workspace role ladder and the access rules derived from it.

Every membership holds exactly one workspace role. Role keys are stable storage
identifiers; display names are what people see. ``idea_submitter`` and
``tenant_admin`` keep their historical keys so existing data, workflow contracts,
and integrations continue to resolve.

    viewer          Viewer            read what a Contributor can read, change nothing
    idea_submitter  Contributor       submit ideas and work on assigned projects
    tenant_admin    Workspace Admin   business configuration, manage Viewers/Contributors
    workspace_owner Workspace Owner   grant Admin/Owner, SSO and security, everything else
"""

from collections.abc import Iterable
from dataclasses import dataclass

VIEWER = "viewer"
CONTRIBUTOR = "idea_submitter"
WORKSPACE_ADMIN = "tenant_admin"
WORKSPACE_OWNER = "workspace_owner"


@dataclass(frozen=True)
class WorkspaceRole:
    key: str
    name: str
    rank: int
    description: str
    permissions: tuple[str, ...]


_CONTRIBUTE = ("idea.view", "idea.create", "project.contribute", "approval.act")
_ADMINISTER = (
    "idea.view_all",
    "project.view_all",
    "audit.view_all",
    "tenant.settings.manage",
    "workflow.publish",
    "tenant.people.manage",
)
_OWN = ("tenant.roles.manage", "tenant.security.manage")

WORKSPACE_ROLES: tuple[WorkspaceRole, ...] = (
    WorkspaceRole(
        VIEWER,
        "Viewer",
        0,
        "Read-only access to what Contributors can see",
        ("idea.view",),
    ),
    WorkspaceRole(
        CONTRIBUTOR,
        "Contributor",
        1,
        "Submit ideas and work on assigned projects",
        _CONTRIBUTE,
    ),
    WorkspaceRole(
        WORKSPACE_ADMIN,
        "Workspace Admin",
        2,
        "Manage configuration, workflows, Viewers and Contributors",
        _CONTRIBUTE + _ADMINISTER,
    ),
    WorkspaceRole(
        WORKSPACE_OWNER,
        "Workspace Owner",
        3,
        "Full control, including roles, sign-in and security",
        _CONTRIBUTE + _ADMINISTER + _OWN,
    ),
)

ROLES_BY_KEY = {role.key: role for role in WORKSPACE_ROLES}
ADMIN_ROLE_KEYS = (WORKSPACE_ADMIN, WORKSPACE_OWNER)
CONTRIBUTING_ROLE_KEYS = (CONTRIBUTOR, WORKSPACE_ADMIN, WORKSPACE_OWNER)


def role_rank(roles: Iterable[str]) -> int:
    """Highest rank held; -1 when the membership holds no known workspace role."""
    return max((ROLES_BY_KEY[key].rank for key in roles if key in ROLES_BY_KEY), default=-1)


def rank_of(role_key: str) -> int:
    role = ROLES_BY_KEY.get(role_key)
    return role.rank if role else -1


def can_contribute(roles: Iterable[str]) -> bool:
    return role_rank(roles) >= ROLES_BY_KEY[CONTRIBUTOR].rank


def is_workspace_admin(roles: Iterable[str]) -> bool:
    return role_rank(roles) >= ROLES_BY_KEY[WORKSPACE_ADMIN].rank


def is_workspace_owner(roles: Iterable[str]) -> bool:
    return role_rank(roles) >= ROLES_BY_KEY[WORKSPACE_OWNER].rank


def can_manage_role(actor_roles: Iterable[str], role_key: str) -> bool:
    """Whether the actor may grant, revoke, or act on a member holding ``role_key``.

    Owners manage every role. Everyone else manages only roles strictly below
    their own, so an Admin can never create or remove another Admin or Owner.
    """
    if role_key not in ROLES_BY_KEY or not is_workspace_admin(actor_roles):
        return False
    if is_workspace_owner(actor_roles):
        return True
    return rank_of(role_key) < role_rank(actor_roles)
