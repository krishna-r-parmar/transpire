/**
 * Workspace role ladder. Keys are the stable backend identifiers; names are what people see.
 * Mirrors backend/app/domains/identity/access.py.
 */
export const workspaceRoles = {
  viewer: { name: "Viewer", rank: 0 },
  idea_submitter: { name: "Contributor", rank: 1 },
  tenant_admin: { name: "Workspace Admin", rank: 2 },
  workspace_owner: { name: "Workspace Owner", rank: 3 },
} as const;

export type WorkspaceRoleKey = keyof typeof workspaceRoles;

const isKnown = (key: string): key is WorkspaceRoleKey => key in workspaceRoles;

export function roleName(key: string) {
  return isKnown(key) ? workspaceRoles[key].name : key.replaceAll("_", " ");
}

export function roleNames(keys: string[]) {
  return keys.map(roleName).join(", ") || "No role assigned";
}

function rank(keys: string[]) {
  return Math.max(-1, ...keys.filter(isKnown).map((key) => workspaceRoles[key].rank));
}

export const canContribute = (keys: string[]) => rank(keys) >= workspaceRoles.idea_submitter.rank;
export const isWorkspaceAdmin = (keys: string[]) => rank(keys) >= workspaceRoles.tenant_admin.rank;
export const isWorkspaceOwner = (keys: string[]) => rank(keys) >= workspaceRoles.workspace_owner.rank;
