"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { consultApi, errorMessage } from "@/lib/consult-client/browser";
import type { Lead, TravelEstimate, WalkChecklist } from "@/lib/consult-client/types";
import { HANDS_ON_LABEL, WALK_ITEMS, formatAcres, totalAcres } from "@/lib/consult-client/view";

type Props = {
  lead: Lead;
  travel: TravelEstimate | null;
  /** The schematic map, rendered on the server. */
  map: ReactNode;
};

export function SiteTab({ lead, travel, map }: Props) {
  const canSave = lead.walk !== null;
  const [walk, setWalk] = useState<WalkChecklist>(lead.walk ?? {});
  const [savedWalk, setSavedWalk] = useState(() => JSON.stringify(lead.walk ?? {}));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [status, setStatus] = useState("");

  const done = WALK_ITEMS.filter((item) => walk[item.key]).length;
  const dirty = JSON.stringify(walk) !== savedWalk;
  const count = (flag: "wet" | "poorSoil" | "shade") => lead.areas.filter((a) => a[flag]).length;

  async function save() {
    setBusy(true);
    setFailure("");
    setStatus("");
    try {
      await consultApi.saveWalk(lead.id, walk);
      setSavedWalk(JSON.stringify(walk));
      setStatus("Saved.");
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cols">
      <div className="stack">
        <section className="card" aria-labelledby="site-map">
          <h2 id="site-map">Site map</h2>
          {lead.areas.length ? (
            map
          ) : (
            <div className="empty">
              <p>No areas to draw yet.</p>
              <Link className="btn" href={`/client/${lead.id}?tab=intake`}>
                Add areas on Intake
              </Link>
            </div>
          )}
        </section>
      </div>

      <div className="stack">
        <section className="card" aria-labelledby="site-facts">
          <h2 id="site-facts">Site facts</h2>
          <dl className="kv">
            <dt>ZIP</dt>
            <dd>{lead.zip || "–"}</dd>
            <dt>Hardiness zone</dt>
            <dd>{lead.zone ?? "–"}</dd>
            <dt>Acres in areas</dt>
            <dd>{lead.areas.length ? formatAcres(totalAcres(lead.areas)) : "–"}</dd>
            <dt>Areas</dt>
            <dd>{lead.areas.length}</dd>
            <dt>Wet areas</dt>
            <dd>{count("wet")}</dd>
            <dt>Poor soil</dt>
            <dd>{count("poorSoil")}</dd>
            <dt>Shaded</dt>
            <dd>{count("shade")}</dd>
            <dt>Hands-on</dt>
            <dd>{lead.handsOn ? HANDS_ON_LABEL[lead.handsOn] : "–"}</dd>
            <dt>Travel, round trip</dt>
            <dd>{travel ? `${Math.round(travel.roundTripMiles)} mi · ${travel.hours} h` : "–"}</dd>
          </dl>
        </section>

        <section className="card stack" aria-labelledby="site-walk">
          <div>
            <h2 id="site-walk">Still needs a walk</h2>
            <p className="muted">
              {done} of {WALK_ITEMS.length} seen on the ground.
            </p>
          </div>
          {canSave ? null : (
            <p className="note warn">
              Odoo has nowhere to keep this list yet, so ticks here will not be saved. Use it as a reminder for now.
            </p>
          )}
          <ul className="checks">
            {WALK_ITEMS.map((item) => (
              <li key={item.key}>
                <label>
                  <input
                    type="checkbox"
                    checked={walk[item.key] === true}
                    onChange={(e) => {
                      setWalk({ ...walk, [item.key]: e.target.checked });
                      setStatus("");
                    }}
                  />
                  {item.label}
                </label>
              </li>
            ))}
          </ul>
          {failure ? (
            <div className="alert" role="alert">
              {failure}
            </div>
          ) : null}
          <div className="row">
            <button type="button" className="btn primary" disabled={!canSave || busy || !dirty} onClick={save}>
              {busy ? "Saving…" : "Save checklist"}
            </button>
            <Link className="btn" href={`/client/${lead.id}?tab=design`}>
              Go to Design
            </Link>
            <span className="saved" role="status">
              {status}
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}
