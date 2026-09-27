// Manual refresh trigger: POST /.netlify/functions/trigger-update
// Writes a refresh request to Netlify Blobs (store "jobs", key "refresh-request").
// A scheduler (outside Netlify) watches this flag, runs the scraper, and writes
// the fresh data to Blobs (store "jobs", key "latest").
// It NEVER triggers a Netlify build/deploy (0 credit).
//
// Rate limit: max 1 request per 10 minutes (tracked via Netlify Blobs).
//
// NOTE: @netlify/blobs must be declared in package.json, otherwise the
// deploy-time bundle cannot resolve the import and the function crashes
// with HTTP 502 before any handler code runs.
import { getStore } from "@netlify/blobs";

const RATE_LIMIT_MS = 10 * 60 * 1000;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...CORS,
    },
  });

// Returns { limited:boolean, waitSec:number }.
// A Blobs failure degrades to "not limited" so the button never 502s.
async function checkRateLimit() {
  try {
    const store = getStore("nursejob-triggers");
    const last = await store.get("last_trigger", { type: "text" });
    const now = Date.now();
    if (last && now - Number(last) < RATE_LIMIT_MS) {
      const waitSec = Math.ceil((RATE_LIMIT_MS - (now - Number(last))) / 1000);
      return { limited: true, waitSec };
    }
    return { limited: false, waitSec: 0 };
  } catch (e) {
    console.warn(
      "trigger-update: Blobs rate-limit check failed, allowing request:",
      e
    );
    return { limited: false, waitSec: 0 };
  }
}

async function markTriggered() {
  try {
    const store = getStore("nursejob-triggers");
    await store.set("last_trigger", String(Date.now()));
  } catch (e) {
    console.warn("trigger-update: Blobs write failed:", e);
  }
}

export default async (req) => {
  try {
    if (req.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (req.method !== "POST") {
      return json({ ok: false, error: "Method not allowed" }, 405);
    }
    const rl = await checkRateLimit();
    if (rl.limited) {
      return json(
        { ok: false, error: `Rate limited: try again in ${rl.waitSec}s` },
        429
      );
    }
    // Signal the external scheduler to run a fresh scrape.
    const store = getStore("jobs");
    const requestedAt = new Date().toISOString();
    await store.setJSON("refresh-request", { requestedAt });
    await markTriggered();
    return json({ ok: true, requested_at: requestedAt });
  } catch (e) {
    console.error("trigger-update failed:", e);
    return json({ ok: false, error: String((e && e.message) || e) }, 500);
  }
};
