import { ConsultError } from "@/lib/consult-client/types";

/** Shown in place of a screen when its data could not be read. */
export function LoadError({ error, what }: { error: unknown; what: string }) {
  const known = error instanceof ConsultError;
  if (!known) console.error(`[consult] could not load ${what}`, error);
  return (
    <div className="card empty" role="alert">
      <h2>We could not load {what}</h2>
      <p>{known ? error.message : "Something went wrong on our side."}</p>
      <p className="muted">Nothing was changed. Reload the page to try again.</p>
    </div>
  );
}
