import assert from "node:assert/strict";
import test from "node:test";
import {
  isTenantScopedPath,
  tenantPath,
  tenantSlugFromPathname,
} from "../lib/tenant-routing.ts";

test("tenant paths carry a stable organisation shortname", () => {
  assert.equal(tenantPath("erc-group", "/ideas/123"), "/t/erc-group/ideas/123");
  assert.equal(tenantSlugFromPathname("/t/erc-group/projects"), "erc-group");
  assert.equal(tenantSlugFromPathname("/t/ERC-GROUP/projects"), "erc-group");
});

test("email domains and malformed shortnames are not route identities", () => {
  assert.equal(tenantSlugFromPathname("/t/erc.example.com/home"), null);
  assert.equal(tenantSlugFromPathname("/t/%E0%A4%A/home"), null);
  assert.equal(tenantSlugFromPathname("/home"), null);
});

test("tenant navigation prefixes application routes but not the public website", () => {
  assert.equal(isTenantScopedPath("/home"), true);
  assert.equal(isTenantScopedPath("/ideas/123?section=approval"), true);
  assert.equal(isTenantScopedPath("/"), false);
  assert.equal(isTenantScopedPath("/#platform"), false);
  assert.equal(isTenantScopedPath("/accept-invitation"), false);
});
