import type { Metadata } from "next";
import Link from "next/link";
import { LoadError } from "@/components/LoadError";
import { TopBar } from "@/components/TopBar";
import { getBackend } from "@/lib/consult-client/backend";
import { CONSULT_STAGES, type ConsultStage, type LeadSummary, type Practice, type ServiceStep } from "@/lib/consult-client/types";
import { NEXT_ACTION, STAGE_LABEL, daysInStage, formatAcres, isStage, totalAcres } from "@/lib/consult-client/view";

export const metadata: Metadata = { title: "Pipeline" };
export const dynamic = "force-dynamic";

const STAGE_BADGE: Partial<Record<ConsultStage, string>> = { intake: "gen", site: "ed", archived: "ghost" };

type Data = { leads: LeadSummary[]; practices: Practice[]; steps: ServiceStep[] };

async function load(): Promise<Data> {
  const backend = getBackend();
  const [leads, practices, steps] = await Promise.all([backend.pipeline(), backend.practices(), backend.steps()]);
  return { leads, practices, steps };
}

export default async function PipelinePage({
  searchParams,
}: {
  searchParams: Promise<{ stage?: string }>;
}) {
  const { stage } = await searchParams;
  const filter = isStage(stage) ? stage : null;

  let data: Data;
  try {
    data = await load();
  } catch (error) {
    return (
      <>
        <TopBar current="pipeline" />
        <main id="main">
          <div className="page-head">
            <h1>Pipeline</h1>
          </div>
          <div className="filters" />
          <LoadError error={error} what="the pipeline" />
        </main>
      </>
    );
  }

  const { leads, practices, steps } = data;
  const practiceName = new Map(practices.map((p) => [p.id, p.name]));
  const stepName = new Map(steps.map((s) => [s.id, s.name]));
  const counts = new Map<ConsultStage, number>();
  for (const lead of leads) counts.set(lead.stage, (counts.get(lead.stage) ?? 0) + 1);
  const shown = filter ? leads.filter((lead) => lead.stage === filter) : leads;
  const now = new Date();

  return (
    <>
      <TopBar current="pipeline" />
      <main id="main">
        <div className="page-head">
          <h1>Pipeline</h1>
          <span className="muted">
            {leads.length} {leads.length === 1 ? "client" : "clients"}
          </span>
          <Link className="btn primary push" href="/client/new">
            New client
          </Link>
        </div>

        <nav className="chips filters" aria-label="Filter by stage">
          <Link className="chip" href="/pipeline" aria-current={filter ? undefined : "true"}>
            All <span className="count">{leads.length}</span>
          </Link>
          {CONSULT_STAGES.map((s) => (
            <Link
              key={s}
              className="chip"
              href={`/pipeline?stage=${s}`}
              aria-current={filter === s ? "true" : undefined}
            >
              {STAGE_LABEL[s]} <span className="count">{counts.get(s) ?? 0}</span>
            </Link>
          ))}
        </nav>

        {shown.length === 0 ? (
          <div className="card empty">
            {leads.length === 0 ? (
              <>
                <h2>No clients yet</h2>
                <p>Start with the first one. Intake takes about ten minutes.</p>
                <Link className="btn primary" href="/client/new">
                  New client
                </Link>
              </>
            ) : (
              <>
                <h2>No one is at {STAGE_LABEL[filter!]} right now</h2>
                <p>
                  <Link href="/pipeline">Show every stage</Link>
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="card scroll">
            <table className="pipeline rows-as-cards" role="table">
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col">Client</th>
                  <th role="columnheader" scope="col">Stage</th>
                  <th role="columnheader" scope="col">Practices by area</th>
                  <th role="columnheader" scope="col" className="num">Acres</th>
                  <th role="columnheader" scope="col">Zone</th>
                  <th role="columnheader" scope="col">Service step</th>
                  <th role="columnheader" scope="col">Next action</th>
                  <th role="columnheader" scope="col" className="num">Days in stage</th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {shown.map((lead) => {
                  const days = daysInStage(lead.stageSince, now);
                  const practicesByArea = lead.areas
                    .map((a) => (a.practiceId ? practiceName.get(a.practiceId) : null) ?? a.name)
                    .filter(Boolean);
                  return (
                    <tr key={lead.id} role="row">
                      <td role="cell" className="wide">
                        <Link className="client" href={`/client/${lead.id}`}>
                          {lead.name || "Unnamed client"}
                        </Link>
                        <div className="muted mono">{lead.zip ? `ZIP ${lead.zip}` : "No ZIP yet"}</div>
                      </td>
                      <td role="cell" data-label="Stage">
                        <span className={`badge ${STAGE_BADGE[lead.stage] ?? ""}`}>{STAGE_LABEL[lead.stage]}</span>
                      </td>
                      <td role="cell" data-label="Practices by area">
                        {practicesByArea.length ? practicesByArea.join(" · ") : <span className="muted">No areas yet</span>}
                      </td>
                      <td role="cell" data-label="Acres" className="num">
                        {lead.areas.length ? formatAcres(totalAcres(lead.areas)) : "–"}
                      </td>
                      <td role="cell" data-label="Zone" className="mono">
                        {lead.zone ?? "–"}
                      </td>
                      <td role="cell" data-label="Service step">
                        {(lead.stepId && stepName.get(lead.stepId)) || <span className="muted">Not set</span>}
                      </td>
                      <td role="cell" data-label="Next action">
                        {NEXT_ACTION[lead.stage]}
                      </td>
                      <td role="cell" data-label="Days in stage" className="num">
                        {days === null ? <span title="Odoo does not send this yet">–</span> : days}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  );
}
