// GET /.netlify/functions/get-jobs
// 回傳 Blobs 入面最新嘅職位數據：{ updatedAt, jobs }
// V2 syntax (export default) 先有自動 Blobs context。

import { getStore } from "@netlify/blobs";

export default async (req, context) => {
  const headers = {
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "Access-Control-Allow-Origin": "*",
  };
  try {
    const store = getStore("jobs");
    const data = await store.get("latest", { type: "json" });
    if (!data || !Array.isArray(data.jobs)) {
      return new Response(JSON.stringify({ updatedAt: null, jobs: [] }), { status: 200, headers });
    }
    return new Response(JSON.stringify(data), { status: 200, headers });
  } catch (err) {
    console.error("get-jobs failed:", err);
    // 出錯時回傳空陣列，等前端 fallback 到內置數據
    return new Response(JSON.stringify({ updatedAt: null, jobs: [] }), { status: 200, headers });
  }
};
