/**
 * Picks the consult data source for this process. Server-only.
 *
 * `CONSULT_FIXTURE=1` serves made-up clients from memory so the app can be
 * built and tested before the Odoo routes reach QA. It is ignored in a
 * production build, the same way the auth bypass is.
 */
import { fixtureBackend } from "./fixture";
import { createOdooBackend, odooConfigFromEnv } from "./odoo";
import type { ConsultBackend } from "./types";

export function fixtureEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return env.CONSULT_FIXTURE === "1" && env.NODE_ENV !== "production";
}

let odoo: ConsultBackend | undefined;

export function getBackend(): ConsultBackend {
  if (fixtureEnabled()) return fixtureBackend;
  return (odoo ??= createOdooBackend(odooConfigFromEnv()));
}
