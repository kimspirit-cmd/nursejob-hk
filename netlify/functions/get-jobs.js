// Read the latest nurse jobs from Netlify Blobs (store "jobs", key "latest").
// Frontend calls: GET /.netlify/functions/get-jobs
// Returns { updatedAt, jobs } — never triggers a deploy (0 credit).
import { getStore } from "@netlify/blobs";

export default async () => {
  try {
    const store = getStore("jobs");
    const data = await store.get("latest", { type: "json" });
    return new Response(
      JSON.stringify(data || { updatedAt: null, jobs: [] }),
      {
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-cache",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  } catch (e) {
    // Don't 500: the frontend falls back to the data baked into the page.
    console.error("get-jobs failed:", e);
    return new Response(
      JSON.stringify({ updatedAt: null, jobs: [], error: "blobs unavailable" }),
      {
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-cache",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  }
};
