import Link from "next/link";
import { headers } from "next/headers";
import { CONSULT_USER_HEADER } from "@/lib/access";
import { fixtureEnabled } from "@/lib/consult-client/backend";

type Props = {
  /** The open client, shown next to Pipeline in the nav. */
  client?: { name: string; href: string };
  current: "pipeline" | "client";
};

export async function TopBar({ client, current }: Props) {
  const user = (await headers()).get(CONSULT_USER_HEADER);
  return (
    <header className="top">
      <span className="brand">Grove Consult</span>
      <nav aria-label="Main">
        <Link href="/pipeline" aria-current={current === "pipeline" ? "page" : undefined}>
          Pipeline
        </Link>
        {client ? (
          <Link href={client.href} aria-current={current === "client" ? "page" : undefined}>
            {client.name}
          </Link>
        ) : null}
      </nav>
      <span className="right">
        {fixtureEnabled() ? (
          <span className="badge gen" title="Made-up clients served from memory, not Odoo">
            Fixture data
          </span>
        ) : null}
        {user ? <span>{user}</span> : null}
      </span>
    </header>
  );
}
