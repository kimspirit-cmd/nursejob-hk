// Daily scheduled refresh, 09:00 HKT (01:00 UTC).
// Fires the Netlify build hook, which rebuilds + redeploys the site.
export const config = { schedule: "0 1 * * *" };

export default async () => {
  const hookUrl = process.env.BUILD_HOOK_URL;
  if (!hookUrl) {
    console.error("scheduled-update: BUILD_HOOK_URL is not configured");
    return new Response("BUILD_HOOK_URL not configured", { status: 500 });
  }
  try {
    const r = await fetch(hookUrl, { method: "POST" });
    console.log("scheduled-update: build hook responded", r.status);
    return new Response(r.ok ? "build triggered" : "build hook failed", {
      status: r.ok ? 200 : 502,
    });
  } catch (e) {
    console.error("scheduled-update failed:", e);
    return new Response(String((e && e.message) || e), { status: 500 });
  }
};
