import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DesignTab } from "@/components/DesignTab";
import { IntakeForm } from "@/components/IntakeForm";
import { LoadError } from "@/components/LoadError";
import { SiteMap } from "@/components/SiteMap";
import { SiteTab } from "@/components/SiteTab";
import { StageMover } from "@/components/StageMover";
import { TopBar } from "@/components/TopBar";
import { getBackend } from "@/lib/consult-client/backend";
import { ConsultError, type ConsultBackend, type Lead } from "@/lib/consult-client/types";
import {
  STAGE_LABEL,
  WORKSPACE_TABS,
  asTab,
  formatAcres,
  tabDone,
  totalAcres,
  type WorkspaceTab,
} from "@/lib/consult-client/view";

export const metadata: Metadata = { title: "Client" };
export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string }> };

async function tabBody(backend: ConsultBackend, lead: Lead, tab: WorkspaceTab) {
  if (tab === "intake") {
    const [modules, practices, steps] = await Promise.all([backend.modules(), backend.practices(), backend.steps()]);
    return <IntakeForm key={lead.id} lead={lead} modules={modules} practices={practices} steps={steps} />;
  }
  if (tab === "site") {
    const [practices, travel] = await Promise.all([
      backend.practices(),
      lead.zip ? backend.travel(lead.zip).catch(() => null) : null,
    ]);
    return <SiteTab lead={lead} travel={travel} map={<SiteMap areas={lead.areas} practices={practices} />} />;
  }
  return <DesignTab leadId={lead.id} initial={await backend.plans(lead.id)} />;
}

export default async function ClientPage({ params, searchParams }: Props) {
  const id = Number((await params).id);
  if (!Number.isInteger(id) || id <= 0) notFound();
  const tab = asTab((await searchParams).tab);
  const href = `/client/${id}`;

  let lead: Lead;
  let body: React.ReactNode;
  try {
    const backend = getBackend();
    lead = await backend.lead(id);
    body = await tabBody(backend, lead, tab);
  } catch (error) {
    if (error instanceof ConsultError && error.status === 404) notFound();
    return (
      <>
        <TopBar current="client" client={{ name: "Client", href }} />
        <main id="main" style={{ marginTop: 16 }}>
          <LoadError error={error} what="this client" />
        </main>
      </>
    );
  }

  return (
    <>
      <TopBar current="client" client={{ name: lead.name || "Unnamed client", href }} />
      <main id="main">
        <div className="client-head">
          <h1>{lead.name || "Unnamed client"}</h1>
          <span className="muted mono">
            {[
              lead.zone ? `Zone ${lead.zone}` : null,
              lead.areas.length ? `${formatAcres(totalAcres(lead.areas))} ac` : null,
              `${lead.areas.length} ${lead.areas.length === 1 ? "area" : "areas"}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
          <span className="badge">{STAGE_LABEL[lead.stage]}</span>
          <StageMover key={lead.stage} leadId={lead.id} stage={lead.stage} />
        </div>
        <nav className="tabs" aria-label="Client workspace">
          {WORKSPACE_TABS.map((t, i) => {
            const done = tabDone(t, lead.stage);
            return (
              <Link
                key={t}
                href={`${href}?tab=${t}`}
                className={done ? "done" : undefined}
                aria-current={t === tab ? "page" : undefined}
              >
                <span className="n" aria-hidden="true">
                  {done ? <i className="tick" /> : i + 1}
                </span>
                {STAGE_LABEL[t]}
                {done ? <span className="sr-only"> (done)</span> : null}
              </Link>
            );
          })}
        </nav>
        {body}
      </main>
    </>
  );
}
