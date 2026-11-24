"use client";

import { useState } from "react";
import { ASPECTS, type Area, type Practice } from "@/lib/consult-client/types";
import { ASPECT_LABEL, blankArea, infraSummary, type LeadErrors } from "@/lib/consult-client/view";

type Props = {
  areas: Area[];
  practices: Practice[];
  errors?: LeadErrors["areas"];
  onChange: (areas: Area[]) => void;
};

const SITE_FLAGS = [
  ["wet", "Wet"],
  ["poorSoil", "Poor soil"],
  ["shade", "Shade"],
] as const;

/**
 * The areas of a property, one row each: a name, the practice going in, its
 * size and what the ground is like. The practice's site needs and default
 * infrastructure show under the picker, read-only.
 */
export function AreasTable({ areas, practices, errors = [], onChange }: Props) {
  const [removed, setRemoved] = useState<{ area: Area; index: number } | null>(null);

  const update = (index: number, patch: Partial<Area>) =>
    onChange(areas.map((area, i) => (i === index ? { ...area, ...patch } : area)));

  const remove = (index: number) => {
    setRemoved({ area: areas[index], index });
    onChange(areas.filter((_, i) => i !== index));
  };

  const undo = () => {
    if (!removed) return;
    const next = [...areas];
    next.splice(Math.min(removed.index, next.length), 0, removed.area);
    onChange(next);
    setRemoved(null);
  };

  return (
    <div className="stack">
      {areas.length === 0 ? (
        <p className="muted">No areas yet. Add one for each part of the land that gets its own practice.</p>
      ) : (
        <table className="areas rows-as-cards" role="table">
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader" scope="col" className="col-name">Area</th>
              <th role="columnheader" scope="col">Practice</th>
              <th role="columnheader" scope="col" className="col-acres">Acres</th>
              <th role="columnheader" scope="col" className="col-aspect">Aspect</th>
              <th role="columnheader" scope="col" className="col-site">Site</th>
              <th role="columnheader" scope="col" className="col-remove">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {areas.map((area, i) => {
              const n = i + 1;
              const err = errors[i] ?? {};
              const practice = practices.find((p) => p.id === area.practiceId);
              return (
                <tr key={i} role="row" aria-label={`Area ${n}`}>
                  <td role="cell" data-label="Area" className="wide">
                    <input
                      aria-label={`Area ${n} name`}
                      aria-invalid={err.name ? true : undefined}
                      aria-describedby={err.name ? `area-${i}-name-err` : undefined}
                      value={area.name}
                      placeholder="Back pasture"
                      onChange={(e) => update(i, { name: e.target.value })}
                    />
                    {err.name ? (
                      <p className="err" id={`area-${i}-name-err`}>
                        {err.name}
                      </p>
                    ) : null}
                  </td>
                  <td role="cell" data-label="Practice" className="wide">
                    <select
                      aria-label={`Area ${n} practice`}
                      aria-invalid={err.practiceId ? true : undefined}
                      aria-describedby={`area-${i}-needs${err.practiceId ? ` area-${i}-practice-err` : ""}`}
                      value={area.practiceId ?? ""}
                      onChange={(e) => update(i, { practiceId: e.target.value ? Number(e.target.value) : null })}
                    >
                      <option value="">Pick a practice</option>
                      {practices.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    {err.practiceId ? (
                      <p className="err" id={`area-${i}-practice-err`}>
                        {err.practiceId}
                      </p>
                    ) : null}
                    <div className="needs" id={`area-${i}-needs`}>
                      {practice ? (
                        <>
                          {practice.siteNeeds ? <p>Needs: {practice.siteNeeds}</p> : null}
                          {practice.infrastructure.length ? (
                            <p>Comes with: {infraSummary(practice.infrastructure)}</p>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  </td>
                  <td role="cell" data-label="Acres">
                    <input
                      aria-label={`Area ${n} acres`}
                      aria-invalid={err.acres ? true : undefined}
                      aria-describedby={err.acres ? `area-${i}-acres-err` : undefined}
                      className="mono"
                      type="number"
                      inputMode="decimal"
                      min="0"
                      step="0.05"
                      value={area.acres || ""}
                      onChange={(e) => update(i, { acres: Number(e.target.value) || 0 })}
                    />
                    {err.acres ? (
                      <p className="err" id={`area-${i}-acres-err`}>
                        {err.acres}
                      </p>
                    ) : null}
                  </td>
                  <td role="cell" data-label="Aspect">
                    <select
                      aria-label={`Area ${n} aspect`}
                      value={area.aspect}
                      onChange={(e) => update(i, { aspect: e.target.value as Area["aspect"] })}
                    >
                      <option value="">Not set</option>
                      {ASPECTS.map((a) => (
                        <option key={a} value={a}>
                          {ASPECT_LABEL[a]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td role="cell" data-label="Site" className="wide">
                    <div className="chips" role="group" aria-label={`Area ${n} site conditions`}>
                      {SITE_FLAGS.map(([flag, label]) => (
                        <button
                          key={flag}
                          type="button"
                          className="chip"
                          aria-pressed={area[flag]}
                          onClick={() => update(i, { [flag]: !area[flag] })}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </td>
                  <td role="cell" className="wide">
                    <button
                      type="button"
                      className="btn quiet small"
                      aria-label={`Remove area ${n}${area.name ? `, ${area.name}` : ""}`}
                      onClick={() => remove(i)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div className="row">
        <button type="button" className="btn small" onClick={() => onChange([...areas, blankArea()])}>
          Add area
        </button>
        <span role="status" className="muted">
          {removed ? (
            <>
              Removed {removed.area.name || "an unnamed area"}.{" "}
              <button type="button" className="btn quiet small" onClick={undo}>
                Undo
              </button>
            </>
          ) : null}
        </span>
      </div>
    </div>
  );
}
