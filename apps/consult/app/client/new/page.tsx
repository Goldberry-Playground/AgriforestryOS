import type { Metadata } from "next";
import { IntakeForm } from "@/components/IntakeForm";
import { LoadError } from "@/components/LoadError";
import { TopBar } from "@/components/TopBar";
import { getBackend } from "@/lib/consult-client/backend";

export const metadata: Metadata = { title: "New client" };
export const dynamic = "force-dynamic";

export default async function NewClientPage() {
  const top = <TopBar current="client" client={{ name: "New client", href: "/client/new" }} />;
  try {
    const backend = getBackend();
    const [modules, practices, steps] = await Promise.all([backend.modules(), backend.practices(), backend.steps()]);
    return (
      <>
        {top}
        <main id="main">
          <div className="client-head">
            <h1>New client</h1>
            <span className="muted">Starts at Intake</span>
          </div>
          <div className="tabs" />
          <IntakeForm lead={null} modules={modules} practices={practices} steps={steps} />
        </main>
      </>
    );
  } catch (error) {
    return (
      <>
        {top}
        <main id="main" style={{ marginTop: 16 }}>
          <LoadError error={error} what="the intake form" />
        </main>
      </>
    );
  }
}
