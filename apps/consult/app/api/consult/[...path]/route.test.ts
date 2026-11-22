import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resetFixture } from "@/lib/consult-client/fixture";
import { GET, POST } from "./route";

vi.stubEnv("CONSULT_FIXTURE", "1");
vi.stubEnv("NODE_ENV", "test");

beforeEach(() => resetFixture());

const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("?")[0].split("/") }) });

function post(path: string, body: unknown, headers: Record<string, string> = {}) {
  const req = new NextRequest(`http://consult.test/api/consult/${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", "sec-fetch-site": "same-origin", ...headers },
    body: JSON.stringify(body),
  });
  return POST(req, ctx(path));
}

const get = (path: string) => GET(new NextRequest(`http://consult.test/api/consult/${path}`), ctx(path));

const client = { name: "Test Acres", zip: "37064", areas: [], moduleIds: [] };

describe("consult BFF", () => {
  it("saves a client and returns it", async () => {
    const res = await post("lead", client);
    expect(res.status).toBe(200);
    expect((await res.json()).lead).toMatchObject({ name: "Test Acres", stage: "intake" });
  });

  it("only serves the routes it lists", async () => {
    expect((await get("pipeline")).status).toBe(404);
    expect((await get("../../grove/api/v1/products")).status).toBe(404);
    expect((await post("lead/101/delete", {})).status).toBe(404);
  });

  it("refuses writes from another site or in another format", async () => {
    expect((await post("lead", client, { "sec-fetch-site": "cross-site" })).status).toBe(403);
    expect((await post("lead", client, { "content-type": "text/plain" })).status).toBe(403);
    const foreign = new NextRequest("http://consult.test/api/consult/lead", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "https://elsewhere.test", host: "consult.test" },
      body: JSON.stringify(client),
    });
    expect((await POST(foreign, ctx("lead"))).status).toBe(403);
  });

  it("validates before it calls the backend", async () => {
    expect((await post("lead", { name: "" })).status).toBe(422);
    expect((await post("lead/101/stage", { stage: "won" })).status).toBe(422);
    expect((await get("zone?zip=abc")).status).toBe(422);
  });

  it("records the verified user on a section edit", async () => {
    await post("lead/102/plan", {});
    const res = await post(
      "lead/102/plan/1/section/site_summary",
      { body: "Seen on foot." },
      { "x-consult-user": "consultant@example.com" },
    );
    expect((await res.json()).section).toMatchObject({ status: "edited", by: "consultant@example.com" });
  });

  it("answers 404 for a client that is not there", async () => {
    expect((await get("lead/999/plans")).status).toBe(404);
  });
});
