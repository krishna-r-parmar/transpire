import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const signInPortal = await readFile(
  new URL("../app/sign-in/sign-in-portal.tsx", import.meta.url),
  "utf8",
);
const signInPage = await readFile(
  new URL("../app/sign-in/page.tsx", import.meta.url),
  "utf8",
);

test("the sign-in form cannot fall back to a credential-bearing GET request", () => {
  const formTag = signInPortal.match(/<form[\s\S]*?>/)?.[0] ?? "";

  assert.match(formTag, /action="\/sign-in"/);
  assert.match(formTag, /method="post"/);
  assert.match(formTag, /aria-busy=\{!hydrated \|\| loading\}/);
  assert.match(
    signInPortal,
    /type="submit" disabled=\{!hydrated \|\| loading\}/,
  );
});

test("credential-bearing sign-in query strings are replaced before rendering", () => {
  assert.match(signInPage, /normalizedKey === "email"/);
  assert.match(signInPage, /normalizedKey === "password"/);
  assert.match(
    signInPage,
    /redirect\(tenantSlug \? tenantPath\(tenantSlug, "\/sign-in"\) : "\/sign-in"\)/,
  );
});
