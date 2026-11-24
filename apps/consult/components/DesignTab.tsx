"use client";

import { useId, useState } from "react";
import { consultApi, errorMessage } from "@/lib/consult-client/browser";
import type { Plan, PlanSection, PlansResult } from "@/lib/consult-client/types";
import { SECTION_STATUS_LABEL, diffWords } from "@/lib/consult-client/view";

const STATUS_BADGE = { generated: "gen", edited: "ed", approved: "" } as const;

type SectionProps = {
  leadId: number;
  version: number;
  section: PlanSection;
  locked: boolean;
  onSaved: () => Promise<void>;
};

function SectionEditor({ leadId, version, section, locked, onSaved }: SectionProps) {
  const uid = useId();
  const [body, setBody] = useState(section.body);
  const [note, setNote] = useState(section.editNote);
  const [showDraft, setShowDraft] = useState(false);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);
  const [failure, setFailure] = useState("");

  const dirty = body !== section.body || note !== section.editNote;
  const changed = body !== section.draftBody;
  const approved = section.status === "approved";

  async function send(approve: boolean) {
    setBusy(approve ? "approve" : "save");
    setFailure("");
    try {
      await consultApi.saveSection(leadId, version, section.key, {
        ...(body !== section.body ? { body } : {}),
        editNote: note,
        ...(approve ? { approve: true } : {}),
      });
      await onSaved();
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="sec" aria-labelledby={`${uid}-title`}>
      <div className="h">
        <h3 id={`${uid}-title`}>{section.title}</h3>
        <span className={`badge ${STATUS_BADGE[section.status]}`}>{SECTION_STATUS_LABEL[section.status]}</span>
        {section.by ? <span className="muted">by {section.by}</span> : null}
      </div>
      <div className="field">
        <label htmlFor={`${uid}-body`}>Section text</label>
        <textarea
          id={`${uid}-body`}
          value={body}
          readOnly={locked}
          rows={Math.min(14, Math.max(4, Math.ceil(body.length / 90)))}
          onChange={(e) => setBody(e.target.value)}
        />
      </div>
      {changed || note ? (
        <div className="field">
          <label htmlFor={`${uid}-note`}>Why I changed it (optional)</label>
          <input id={`${uid}-note`} value={note} readOnly={locked} onChange={(e) => setNote(e.target.value)} />
        </div>
      ) : null}
      {showDraft ? (
        <div className="diff" id={`${uid}-diff`} aria-label="Changes from the draft">
          {changed ? (
            diffWords(section.draftBody, body).map((part, i) =>
              part.kind === "same" ? (
                <span key={i}>{part.text}</span>
              ) : part.kind === "removed" ? (
                <del key={i}>{part.text}</del>
              ) : (
                <ins key={i}>{part.text}</ins>
              ),
            )
          ) : (
            <span className="muted">This section still reads as it was drafted.</span>
          )}
        </div>
      ) : null}
      {failure ? (
        <div className="alert" role="alert">
          {failure}
        </div>
      ) : null}
      <div className="row">
        {locked ? null : (
          <>
            <button type="button" className="btn small" disabled={!dirty || busy !== null} onClick={() => send(false)}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="btn small primary"
              disabled={busy !== null || (approved && !dirty)}
              onClick={() => send(true)}
            >
              {busy === "approve" ? "Approving…" : approved && !dirty ? "Approved" : "Approve"}
            </button>
          </>
        )}
        <button
          type="button"
          className="btn small quiet"
          aria-expanded={showDraft}
          aria-controls={showDraft ? `${uid}-diff` : undefined}
          onClick={() => setShowDraft(!showDraft)}
        >
          {showDraft ? "Hide draft" : "Show draft"}
        </button>
        {dirty && !locked ? <span className="muted">Unsaved changes</span> : null}
      </div>
    </article>
  );
}

export function DesignTab({ leadId, initial }: { leadId: number; initial: PlansResult }) {
  const [plans, setPlans] = useState<Plan[]>(initial.plans);
  const [version, setVersion] = useState<number | null>(initial.plans.at(-1)?.version ?? null);
  const [busy, setBusy] = useState<"new" | "approve" | null>(null);
  const [failure, setFailure] = useState("");

  const plan = plans.find((p) => p.version === version) ?? null;

  async function reload() {
    setPlans((await consultApi.plans(leadId)).plans);
  }

  async function run(kind: "new" | "approve", action: () => Promise<void>) {
    setBusy(kind);
    setFailure("");
    try {
      await action();
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const newVersion = () =>
    run("new", async () => {
      const { plan: created } = await consultApi.createPlan(leadId);
      await reload();
      setVersion(created.version);
    });

  const approvePlan = () =>
    run("approve", async () => {
      if (!plan) return;
      await consultApi.approvePlan(leadId, plan.version);
      await reload();
    });

  if (!initial.readable) {
    return (
      <div className="card empty">
        <h2>Plans cannot be opened here yet</h2>
        <p>Odoo keeps the plan sections, but it does not hand them back to this screen yet.</p>
        <p className="muted">Nothing is lost. This tab fills in as soon as that route ships.</p>
      </div>
    );
  }

  const alert = failure ? (
    <div className="alert" role="alert">
      {failure}
    </div>
  ) : null;

  if (!plan) {
    return (
      <div className="card empty">
        <h2>No plan yet</h2>
        <p>Start version 1. It lays out one section for each goal module, ready for you to write.</p>
        <button type="button" className="btn primary" disabled={busy !== null} onClick={newVersion}>
          {busy === "new" ? "Starting…" : "Start plan v1"}
        </button>
        {alert}
      </div>
    );
  }

  const locked = plan.status !== "draft";
  const approvedCount = plan.sections.filter((s) => s.status === "approved").length;
  const allApproved = plan.sections.length > 0 && approvedCount === plan.sections.length;

  return (
    <div className="cols">
      <section className="card stack" aria-labelledby="plan-sections">
        <div className="row">
          <h2 id="plan-sections" style={{ margin: 0 }}>
            Plan v{plan.version}
          </h2>
          <span className={`badge ${locked ? "" : "ghost"}`}>{locked ? `${plan.status}, locked` : "Draft"}</span>
        </div>
        {locked ? (
          <p className="note">This version is approved and locked. Start a new version to change it.</p>
        ) : null}
        {plan.sections.map((section) => (
          <SectionEditor
            key={`${plan.version}:${section.key}:${section.status}:${section.body.length}`}
            leadId={leadId}
            version={plan.version}
            section={section}
            locked={locked}
            onSaved={reload}
          />
        ))}
      </section>

      <div className="stack">
        <section className="card stack" aria-labelledby="plan-versions">
          <h2 id="plan-versions" style={{ margin: 0 }}>
            Versions
          </h2>
          <div className="chips" role="group" aria-labelledby="plan-versions">
            {plans.map((p) => (
              <button
                key={p.version}
                type="button"
                className="chip"
                aria-pressed={p.version === plan.version}
                onClick={() => setVersion(p.version)}
              >
                v{p.version} · {p.status}
              </button>
            ))}
          </div>
          <div>
            <button type="button" className="btn small" disabled={busy !== null} onClick={newVersion}>
              {busy === "new" ? "Starting…" : "New plan version"}
            </button>
          </div>
        </section>

        <section className="card stack" aria-labelledby="plan-approve">
          <h2 id="plan-approve" style={{ margin: 0 }}>
            Approval
          </h2>
          <p className="mono">
            {approvedCount} of {plan.sections.length} sections approved
          </p>
          <div className="prog" aria-hidden="true">
            <i style={{ width: `${plan.sections.length ? (approvedCount / plan.sections.length) * 100 : 0}%` }} />
          </div>
          {locked ? null : (
            <>
              <p className="muted" id="plan-approve-hint">
                {allApproved
                  ? "Every section is approved. Approving the plan locks this version."
                  : "The plan can be approved once every section is."}
              </p>
              <div>
                <button
                  type="button"
                  className="btn primary"
                  disabled={!allApproved || busy !== null}
                  aria-describedby="plan-approve-hint"
                  onClick={approvePlan}
                >
                  {busy === "approve" ? "Approving…" : "Approve plan"}
                </button>
              </div>
            </>
          )}
          {alert}
        </section>
      </div>
    </div>
  );
}
