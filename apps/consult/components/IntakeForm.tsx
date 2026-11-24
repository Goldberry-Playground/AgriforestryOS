"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { AreasTable } from "@/components/AreasTable";
import { consultApi, errorMessage } from "@/lib/consult-client/browser";
import {
  HANDS_ON,
  type GoalModule,
  type HandsOn,
  type Lead,
  type LeadInput,
  type Practice,
  type ServiceStep,
  type TravelEstimate,
} from "@/lib/consult-client/types";
import {
  HANDS_ON_LABEL,
  ZIP_PATTERN,
  formatAcres,
  hasErrors,
  totalAcres,
  validateLead,
  type LeadErrors,
} from "@/lib/consult-client/view";

type Props = {
  /** Null for a new client. */
  lead: Lead | null;
  modules: GoalModule[];
  practices: Practice[];
  steps: ServiceStep[];
};

function toInput(lead: Lead | null): LeadInput {
  return {
    id: lead?.id,
    name: lead?.name ?? "",
    zip: lead?.zip ?? "",
    handsOn: lead?.handsOn ?? "",
    stepId: lead?.stepId ?? null,
    goals: lead?.goals ?? "",
    existing: lead?.existing ?? "",
    moduleIds: lead?.moduleIds ?? [],
    areas: lead?.areas ?? [],
  };
}

function travelText(t: TravelEstimate): string {
  return [
    `${Math.round(t.roundTripMiles)} mi round trip`,
    `${t.billableHours} h billable`,
    t.overnight ? "overnight" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

type ZipLookup =
  | { state: "idle" | "loading" }
  | { state: "done"; zone: string | null; travel: TravelEstimate | null };

export function IntakeForm({ lead, modules, practices, steps }: Props) {
  const router = useRouter();
  const uid = useId();
  const [form, setForm] = useState<LeadInput>(() => toInput(lead));
  const [saved, setSaved] = useState(() => JSON.stringify(toInput(lead)));
  const [errors, setErrors] = useState<LeadErrors>({ areas: [] });
  const [busy, setBusy] = useState<"save" | "next" | null>(null);
  const [failure, setFailure] = useState("");
  const [status, setStatus] = useState("");
  const [lookup, setLookup] = useState<ZipLookup>({ state: "idle" });
  const summaryRef = useRef<HTMLDivElement>(null);

  const dirty = useMemo(() => JSON.stringify(form) !== saved, [form, saved]);
  const set = (patch: Partial<LeadInput>) => {
    setForm((f) => ({ ...f, ...patch }));
    setStatus("");
  };

  // Zone and travel follow the ZIP as soon as it is a whole ZIP.
  useEffect(() => {
    if (!ZIP_PATTERN.test(form.zip)) {
      setLookup({ state: "idle" });
      return;
    }
    let live = true;
    setLookup({ state: "loading" });
    const timer = setTimeout(async () => {
      const [zone, travel] = await Promise.all([
        consultApi.zone(form.zip).then((r) => r.zone, () => null),
        consultApi.travel(form.zip).then((r) => r.travel, () => null),
      ]);
      if (live) setLookup({ state: "done", zone, travel });
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [form.zip]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save(then: "save" | "next") {
    const found = validateLead(form);
    setErrors(found);
    setFailure("");
    setStatus("");
    if (hasErrors(found)) {
      requestAnimationFrame(() => summaryRef.current?.focus());
      return;
    }
    setBusy(then);
    try {
      const result = await consultApi.saveLead(form);
      const next = toInput(result.lead);
      setForm(next);
      setSaved(JSON.stringify(next));
      setStatus(
        result.notKept.length
          ? `Saved, but Odoo did not keep the ${result.notKept.join(" or the ")} yet.`
          : "Saved.",
      );
      const base = `/client/${result.lead.id}`;
      if (then === "next") router.push(`${base}?tab=site`);
      else if (!lead) router.replace(base);
      else router.refresh();
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void save("next");
  };

  const toggleModule = (id: number) =>
    set({
      moduleIds: form.moduleIds.includes(id)
        ? form.moduleIds.filter((m) => m !== id)
        : [...form.moduleIds, id],
    });

  const problemCount =
    (errors.name ? 1 : 0) + (errors.zip ? 1 : 0) + errors.areas.reduce((n, row) => n + Object.keys(row).length, 0);
  const acres = totalAcres(form.areas);

  return (
    <form className="stack" onSubmit={onSubmit} noValidate aria-label="Intake">
      <div className="cols">
        <section className="card" aria-labelledby={`${uid}-client`}>
          <h2 id={`${uid}-client`}>Client and land</h2>
          <div className="f2">
            <div className="field">
              <label htmlFor={`${uid}-name`}>Client</label>
              <input
                id={`${uid}-name`}
                value={form.name}
                required
                autoComplete="off"
                aria-invalid={errors.name ? true : undefined}
                aria-describedby={errors.name ? `${uid}-name-err` : undefined}
                onChange={(e) => set({ name: e.target.value })}
              />
              {errors.name ? (
                <p className="err" id={`${uid}-name-err`}>
                  {errors.name}
                </p>
              ) : null}
            </div>
            <div className="field">
              <label htmlFor={`${uid}-zip`}>ZIP</label>
              <input
                id={`${uid}-zip`}
                className="mono"
                value={form.zip}
                inputMode="numeric"
                maxLength={5}
                autoComplete="off"
                aria-invalid={errors.zip ? true : undefined}
                aria-describedby={`${uid}-zone${errors.zip ? ` ${uid}-zip-err` : ""}`}
                onChange={(e) => set({ zip: e.target.value.replace(/\D/g, "") })}
              />
              {errors.zip ? (
                <p className="err" id={`${uid}-zip-err`}>
                  {errors.zip}
                </p>
              ) : null}
              <p className="hint" id={`${uid}-zone`} aria-live="polite">
                {lookup.state === "loading"
                  ? "Looking up the zone…"
                  : lookup.state === "done"
                    ? lookup.zone
                      ? `Zone ${lookup.zone}`
                      : "No zone on file for that ZIP."
                    : "Five digits. The hardiness zone follows from it."}
              </p>
            </div>
            <div className="field">
              <span className="label" id={`${uid}-acres`}>
                Acres in areas
              </span>
              <output className="mono" aria-labelledby={`${uid}-acres`}>
                {form.areas.length ? formatAcres(acres) : "–"}
              </output>
            </div>
            <div className="field">
              <span className="label" id={`${uid}-travel`}>
                Travel estimate
              </span>
              <output className="mono" aria-labelledby={`${uid}-travel`} aria-live="polite">
                {lookup.state === "done" && lookup.travel
                  ? travelText(lookup.travel)
                  : lookup.state === "loading"
                    ? "…"
                    : "–"}
              </output>
            </div>
            <div className="field">
              <label htmlFor={`${uid}-step`}>Service step</label>
              <select
                id={`${uid}-step`}
                value={form.stepId ?? ""}
                disabled={steps.length === 0}
                aria-describedby={steps.length === 0 ? `${uid}-step-hint` : undefined}
                onChange={(e) => set({ stepId: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">Not set</option>
                {steps.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.price ? ` ($${s.price.toLocaleString("en-US")})` : ""}
                  </option>
                ))}
              </select>
              {steps.length === 0 ? (
                <p className="hint" id={`${uid}-step-hint`}>
                  Odoo does not list the service steps yet.
                </p>
              ) : null}
            </div>
            <div className="field">
              <label htmlFor={`${uid}-hands`}>How hands-on</label>
              <select
                id={`${uid}-hands`}
                value={form.handsOn}
                onChange={(e) => set({ handsOn: e.target.value as HandsOn | "" })}
              >
                <option value="">Not set</option>
                {HANDS_ON.map((h) => (
                  <option key={h} value={h}>
                    {HANDS_ON_LABEL[h]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="field" style={{ marginTop: 10 }}>
            <label htmlFor={`${uid}-goals`}>Goals</label>
            <textarea
              id={`${uid}-goals`}
              value={form.goals}
              placeholder="What they want from the land, in their words."
              onChange={(e) => set({ goals: e.target.value })}
            />
          </div>
          <div className="field" style={{ marginTop: 10 }}>
            <label htmlFor={`${uid}-existing`}>What they already have</label>
            <textarea
              id={`${uid}-existing`}
              value={form.existing}
              placeholder="Trees, water, fence, equipment."
              onChange={(e) => set({ existing: e.target.value })}
            />
          </div>
        </section>

        <div className="stack">
          <section className="card" aria-labelledby={`${uid}-modules`}>
            <h2 id={`${uid}-modules`}>Goal modules</h2>
            <p className="muted" style={{ marginBottom: 8 }}>
              Each one you pick becomes a section of the plan. {form.moduleIds.length} picked.
            </p>
            <div className="chips" role="group" aria-labelledby={`${uid}-modules`}>
              {modules.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className="chip"
                  aria-pressed={form.moduleIds.includes(m.id)}
                  title={m.objective || undefined}
                  onClick={() => toggleModule(m.id)}
                >
                  {m.name}
                </button>
              ))}
            </div>
          </section>

          <section className="card" aria-labelledby={`${uid}-records`}>
            <h2 id={`${uid}-records`}>What this stage records</h2>
            <ul className="list-plain muted">
              <li>Who the client is and where the land sits</li>
              <li>Each area, its practice, size and ground</li>
              <li>The goal modules the plan will cover</li>
            </ul>
          </section>
        </div>
      </div>

      <section className="card" aria-labelledby={`${uid}-areas`}>
        <h2 id={`${uid}-areas`}>Areas and practices</h2>
        <AreasTable
          areas={form.areas}
          practices={practices}
          errors={errors.areas}
          onChange={(areas) => set({ areas })}
        />
      </section>

      <div className="card save-bar">
        {problemCount > 0 ? (
          <div className="alert" role="alert" tabIndex={-1} ref={summaryRef}>
            {problemCount === 1 ? "One thing needs fixing" : `${problemCount} things need fixing`} before this can be
            saved. Each is marked above.
          </div>
        ) : null}
        {failure ? (
          <div className="alert" role="alert">
            {failure} Your entries are still here.
          </div>
        ) : null}
        <button type="submit" className="btn primary" disabled={busy !== null}>
          {busy === "next" ? "Saving…" : "Save and go to Site"}
        </button>
        <button type="button" className="btn" disabled={busy !== null} onClick={() => void save("save")}>
          {busy === "save" ? "Saving…" : "Save"}
        </button>
        <span className="saved" role="status">
          {status || (dirty && lead ? <span className="muted">Unsaved changes</span> : null)}
        </span>
      </div>
    </form>
  );
}
