// Manual refresh trigger: POST /.netlify/functions/trigger-update
// Rate limit: max 1 trigger per 10 minutes (tracked via Netlify Blobs).
// Fires the Netlify build hook, which rebuilds + redeploys the site.
import { getStore } from "@netlify/blobs";

const RATE_LIMIT_MS = 10 * 60 * 1000;

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });

export default async (req) => {
  if (req.method !== "POST") {
    return json({ ok: false, error: "Method not allowed" }, 405);
  }
  const hookUrl = process.env.BUILD_HOOK_URL;
  if (!hookUrl) {
    return json({ ok: false, error: "BUILD_HOOK_URL is not configured" }, 500);
  }
  try {
    const store = getStore("nursejob-triggers");
    const last = await store.get("last_trigger", { type: "text" });
    const now = Date.now();
    if (last && now - Number(last) < RATE_LIMIT_MS) {
      const waitSec = Math.ceil((RATE_LIMIT_MS - (now - Number(last))) / 1000);
      return json(
        { ok: false, error: `Rate limited: try again in ${waitSec}s` },
        429
      );
    }
    await store.set("last_trigger", String(now));
    const r = await fetch(hookUrl, { method: "POST" });
    if (!r.ok) {
      throw new Error(`build hook responded HTTP ${r.status}`);
    }
    return json({ ok: true, triggered_at: new Date(now).toISOString() });
  } catch (e) {
    console.error("trigger-update failed:", e);
    return json({ ok: false, error: String((e && e.message) || e) }, 500);
  }
};
