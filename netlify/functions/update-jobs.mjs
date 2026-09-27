// POST /.netlify/functions/update-jobs
// VM 推送最新職位數據寫入 Blobs（唔經 deploy）。
// Body: { secret, action: "update", updatedAt, jobs }
//       { secret, action: "check" }  -> 回傳 { refreshRequested: bool }
// secret 必須同 Netlify env JOBS_UPDATE_SECRET 一致。
// V2 syntax (export default) 先有自動 Blobs context。

import { getStore } from "@netlify/blobs";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...CORS },
  });

export default async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS });
  }
  if (req.method !== "POST") {
    return json({ ok: false, error: "Method not allowed" }, 405);
  }

  let body;
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "Bad JSON" }, 400);
  }

  const secret = Netlify.env.get("JOBS_UPDATE_SECRET");
  if (!secret || body.secret !== secret) {
    return json({ ok: false, error: "Forbidden" }, 403);
  }

  const store = getStore("jobs");

  try {
    if (body.action === "check") {
      const flag = await store.get("refresh-request", { type: "json" });
      const latest = (await store.get("latest", { type: "json" })) || {};
      const requested = !!(flag && flag.requestedAt && flag.requestedAt > (latest.updatedAt || ""));
      return json({ refreshRequested: requested });
    }

    if (body.action === "update") {
      if (!body.updatedAt || !Array.isArray(body.jobs)) {
        return json({ ok: false, error: "Missing updatedAt/jobs" }, 400);
      }
      await store.setJSON("latest", { updatedAt: body.updatedAt, jobs: body.jobs });
      try { await store.delete("refresh-request"); } catch {}
      return json({ ok: true, count: body.jobs.length });
    }

    return json({ ok: false, error: "Unknown action" }, 400);
  } catch (err) {
    console.error("update-jobs failed:", err);
    return json({ ok: false, error: "Blobs operation failed" }, 500);
  }
};
