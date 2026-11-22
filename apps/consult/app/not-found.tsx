import Link from "next/link";
import { TopBar } from "@/components/TopBar";

export default function NotFound() {
  return (
    <>
      <TopBar current="pipeline" />
      <main id="main" style={{ marginTop: 16 }}>
        <div className="card empty">
          <h1>That client is not in the pipeline</h1>
          <p>They may have been archived, or the link is off by a digit.</p>
          <Link className="btn primary" href="/pipeline">
            Back to the pipeline
          </Link>
        </div>
      </main>
    </>
  );
}
