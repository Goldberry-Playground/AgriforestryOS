"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { consultApi, errorMessage } from "@/lib/consult-client/browser";
import { CONSULT_STAGES, type ConsultStage } from "@/lib/consult-client/types";
import { STAGE_LABEL } from "@/lib/consult-client/view";

/** Moves a client to another stage of the pipeline. */
export function StageMover({ leadId, stage }: { leadId: number; stage: ConsultStage }) {
  const router = useRouter();
  const uid = useId();
  const [target, setTarget] = useState<ConsultStage>(stage);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  async function move() {
    setBusy(true);
    setFailure("");
    try {
      await consultApi.setStage(leadId, target);
      router.refresh();
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="push">
      <div>
        <label htmlFor={uid}>Stage</label>
        <select id={uid} value={target} onChange={(e) => setTarget(e.target.value as ConsultStage)}>
          {CONSULT_STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABEL[s]}
            </option>
          ))}
        </select>
      </div>
      <button type="button" className="btn" disabled={busy || target === stage} onClick={move}>
        {busy ? "Moving…" : "Move"}
      </button>
      {failure ? (
        <span className="err" role="alert">
          {failure}
        </span>
      ) : null}
    </div>
  );
}
