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

// 清理 logo 欄位：唔存 base64，只接受短 URL；超過 10KB 一律設 null，
// 防止超大 base64/HTML 導致瀏覽器解碼失敗出彩虹 glitch。
function sanitizeLogo(value) {
  if (value == null) return null;
  const s = String(value).trim();
  if (!s) return null;
  if (s.length > 10 * 1024) return null; // 超過 10KB
  if (/^data:image\//i.test(s)) return null; // data URI base64
  if (/^data:text\/html/i.test(s)) return null; // 包咗 HTML
  // 長串疑似裸 base64（無 data: 前綴）
  if (s.length > 500 && /^[A-Za-z0-9+/=\s]+$/.test(s)) return null;
  // 只接受 http(s) URL
  if (!/^https?:\/\//i.test(s)) return null;
  return s;
}

function sanitizeJobs(jobs) {
  return jobs.map((j) => {
    if (j && typeof j === "object") {
      const out = { ...j };
      for (const k of ["logo", "logo_url", "logoUrl", "image", "image_url", "company_logo"]) {
        if (k in out) out[k] = sanitizeLogo(out[k]);
      }
      // 順手清埋其他欄位入面嘅 data: URI
      for (const k of ["description", "requirements"]) {
        if (typeof out[k] === "string" && /data:image\//i.test(out[k])) {
          out[k] = out[k].replace(/data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/gi, "");
        }
      }
      return out;
    }
    return j;
  });
}

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
      const cleanJobs = sanitizeJobs(body.jobs);
      await store.setJSON("latest", { updatedAt: body.updatedAt, jobs: cleanJobs });
      try { await store.delete("refresh-request"); } catch {}
      return json({ ok: true, count: cleanJobs.length });
    }

    return json({ ok: false, error: "Unknown action" }, 400);
  } catch (err) {
    console.error("update-jobs failed:", err);
    return json({ ok: false, error: "Blobs operation failed" }, 500);
  }
};
