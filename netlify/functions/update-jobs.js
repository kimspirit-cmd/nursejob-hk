// POST /.netlify/functions/update-jobs
// VM 推送最新職位數據寫入 Blobs（唔經 deploy）。
// Body: { secret, action: "update", updatedAt, jobs }
//       { secret, action: "check" }  -> 回傳 { refreshRequested: bool }
// secret 必須同 Netlify env JOBS_UPDATE_SECRET 一致。

const { getStore } = require("@netlify/blobs");

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers: CORS, body: "" };
  }
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers: CORS, body: "Method Not Allowed" };
  }

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, headers: CORS, body: "Bad JSON" };
  }

  const secret = process.env.JOBS_UPDATE_SECRET;
  if (!secret || body.secret !== secret) {
    return { statusCode: 403, headers: CORS, body: "Forbidden" };
  }

  const store = getStore("jobs");

  try {
    if (body.action === "check") {
      const flag = await store.get("refresh-request", { type: "json" });
      const latest = (await store.get("latest", { type: "json" })) || {};
      const requested = !!(flag && flag.requestedAt && flag.requestedAt > (latest.updatedAt || ""));
      return {
        statusCode: 200,
        headers: { ...CORS, "Content-Type": "application/json" },
        body: JSON.stringify({ refreshRequested: requested }),
      };
    }

    if (body.action === "update") {
      if (!body.updatedAt || !Array.isArray(body.jobs)) {
        return { statusCode: 400, headers: CORS, body: "Missing updatedAt/jobs" };
      }
      await store.setJSON("latest", { updatedAt: body.updatedAt, jobs: body.jobs });
      // 清除手動更新旗標
      try { await store.delete("refresh-request"); } catch {}
      return {
        statusCode: 200,
        headers: { ...CORS, "Content-Type": "application/json" },
        body: JSON.stringify({ ok: true, count: body.jobs.length }),
      };
    }

    return { statusCode: 400, headers: CORS, body: "Unknown action" };
  } catch (err) {
    console.error("update-jobs failed:", err);
    return { statusCode: 500, headers: CORS, body: "Blobs operation failed" };
  }
};
