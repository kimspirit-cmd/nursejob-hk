// Manual refresh trigger: POST /.netlify/functions/trigger-update
// Rate limit: max 1 trigger per 10 minutes (tracked via Netlify Blobs).
// Fires the Netlify build hook, which rebuilds + redeploys the site.
//
// NOTE: @netlify/blobs must be declared in package.json, otherwise the
// deploy-time bundle cannot resolve the import and the function crashes
// with HTTP 502 before any handler code runs.
import { getStore } from "@netlify/blobs";

const RATE_LIMIT_MS = 10 * 60 * 1000;
const HOOK_TIMEOUT_MS = 8000; // stay well under the 10s Starter function limit

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
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

// Fire the build hook with an abort timeout so a hanging hook
// can never push us past the function execution limit.
async function fireHook(hookUrl) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HOOK_TIMEOUT_MS);
  try {
    const r = await fetch(hookUrl, { method: "POST", signal: ctrl.signal });
    if (!r.ok) {
      return new Error(`build hook responded HTTP ${r.status}`);
    }
    return null;
  } catch (e) {
    return e && e.name === "AbortError"
      ? new Error("build hook request timed out")
      : e;
  } finally {
    clearTimeout(timer);
  }
}

export default async (req) => {
  try {
    if (req.method !== "POST") {
      return json({ ok: false, error: "Method not allowed" }, 405);
    }
    const hookUrl = process.env.BUILD_HOOK_URL;
    if (!hookUrl) {
      console.error("trigger-update: BUILD_HOOK_URL is not configured");
      return json(
        { ok: false, error: "BUILD_HOOK_URL is not configured" },
        500
      );
    }
    const rl = await checkRateLimit();
    if (rl.limited) {
      return json(
        { ok: false, error: `Rate limited: try again in ${rl.waitSec}s` },
        429
      );
    }
    const hookErr = await fireHook(hookUrl);
    if (hookErr) {
      console.error("trigger-update: build hook failed:", hookErr);
      return json({ ok: false, error: String(hookErr.message || hookErr) }, 502);
    }
    await markTriggered();
    return json({ ok: true, triggered_at: new Date().toISOString() });
  } catch (e) {
    console.error("trigger-update failed:", e);
    return json({ ok: false, error: String((e && e.message) || e) }, 500);
  }
};
