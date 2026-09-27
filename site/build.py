"""Build the static site: read data/jobs.json -> write dist/index.html + dist/version.json.

Same page design/content as the original artifact page (filters, 今日新職
badge, stats, hash-routed detail view), plus:
- sticky header with top-right 「最後更新」 timestamp + 「🔄 更新職位」 button
- PWA head links (manifest + icons)
"""
import html as htmlmod
import json
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "jobs.json"
DIST = ROOT / "dist"
OUT = DIST / "index.html"
VERSION = DIST / "version.json"

HKT = timezone(timedelta(hours=8))

SOURCE_NAMES = {"gov": "勞工處", "jump": "明報 JUMP", "ctgoodjobs": "CTgoodjobs", "csb": "公務員事務局", "plk": "保良局"}
SOURCE_URLS = {
    "gov": "https://www1.jobs.gov.hk/0/en/jobseeker/jobsearch/search/",
    "jump": "https://jump.mingpao.com/",
    "ctgoodjobs": "https://www.ctgoodjobs.hk/",
    "csb": "https://csboa2.csb.gov.hk/csboa/jve/JVE_001_text.action?languageType=1",
}


def esc(s) -> str:
    return htmlmod.escape(s or "", quote=True)


def slugify(source: str, external_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", f"{source}-{external_id}").strip("-").lower()


CSS = """
:root{--bg:#f6f8fb;--card:#fff;--ink:#1c2733;--muted:#64748b;--brand:#0e7c6b;
--brand-d:#0a5f52;--line:#e5eaf0;--tag:#e8f3f0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,'Segoe UI','Noto Sans TC','PingFang HK','Microsoft JhengHei',sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header{background:linear-gradient(135deg,#0e7c6b,#0a5f52);color:#fff;padding:20px 0;position:sticky;top:0;z-index:20}
.headrow{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
header h1{margin:0;font-size:24px}header p{margin:6px 0 0;opacity:.9;font-size:13px}
.headright{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
#lastUpdated{font-size:13px;opacity:.92;white-space:nowrap}
#refreshBtn{background:#fff;color:#0a5f52;border:none;border-radius:10px;padding:10px 16px;
font-size:15px;font-weight:700;cursor:pointer;white-space:nowrap}
#refreshBtn:hover{background:#e8f3f0}
#refreshBtn:disabled{opacity:.75;cursor:wait}
#refreshMsg{font-size:13px;max-width:260px}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid rgba(10,95,82,.25);
border-top-color:#0a5f52;border-radius:50%;animation:spin .8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 16px;min-width:110px}
.stat b{font-size:22px;color:var(--brand-d)}.stat span{display:block;font-size:12px;color:var(--muted)}
.toolbar{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:14px 0;
display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.toolbar input[type=search]{flex:1;min-width:200px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:15px}
.toolbar select{padding:10px;border:1px solid var(--line);border-radius:10px;font-size:14px;background:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin:14px 0 30px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:8px}
.card h3{margin:0;font-size:17px;line-height:1.4}.card h3 a{color:var(--ink);text-decoration:none;cursor:pointer}
.card h3 a:hover{color:var(--brand-d)}
.meta{font-size:13px;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap}
.tags{display:flex;gap:6px;flex-wrap:wrap}
.tag{font-size:12px;background:var(--tag);color:var(--brand-d);border-radius:20px;padding:3px 10px}
.tag.src{background:#eef2f7;color:#475569}
.tag.new{background:#fee2e2;color:#b91c1c;font-weight:700}
.chk{font-size:14px;display:flex;align-items:center;gap:6px;white-space:nowrap;cursor:pointer}
.salary{font-weight:700;color:#b45309}
footer{color:var(--muted);font-size:12px;padding:24px 0;text-align:center}
footer a{color:var(--brand-d)}
.detail{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0}
.detail h1{margin:0 0 8px;font-size:24px}
.kv{display:grid;grid-template-columns:110px 1fr;gap:8px 12px;font-size:14px;margin:14px 0}
.kv dt{color:var(--muted)}.kv dd{margin:0}
.apply{display:inline-block;background:var(--brand);color:#fff;padding:12px 22px;border-radius:10px;
text-decoration:none;font-weight:700;margin-top:8px}.apply:hover{background:var(--brand-d)}
.back{display:inline-block;margin:14px 0;color:var(--brand-d);text-decoration:none;font-size:14px;cursor:pointer}
pre.desc{white-space:pre-wrap;font-family:inherit;font-size:14px;line-height:1.7;background:#fafbfc;
border:1px solid var(--line);border-radius:10px;padding:14px}
.empty{text-align:center;color:var(--muted);padding:40px}
.count{font-size:13px;color:var(--muted);margin:4px 0}
@media(max-width:640px){.kv{grid-template-columns:90px 1fr}header h1{font-size:20px}
#refreshBtn{padding:8px 12px;font-size:14px}#lastUpdated{font-size:12px}}
"""

JS = """
<script>
let JOBS = /*__JOBS__*/[];
/* Live data: prefer Netlify Blobs via get-jobs; fall back to baked-in data. */
async function loadLiveJobs(){
  try{
    const r=await fetch('/.netlify/functions/get-jobs',{cache:'no-store'});
    if(!r.ok)return false;
    const d=await r.json();
    if(!d||!Array.isArray(d.jobs)||!d.jobs.length)return false;
    JOBS=d.jobs;
    const lu=document.getElementById('lastUpdated');
    if(lu&&d.updatedAt){
      lu.dataset.ts=d.updatedAt;
      try{
        const dt=new Date(d.updatedAt),p=n=>String(n).padStart(2,'0');
        lu.textContent='最後更新：'+dt.getFullYear()+'-'+p(dt.getMonth()+1)+'-'+p(dt.getDate())+' '+p(dt.getHours())+':'+p(dt.getMinutes());
      }catch(e){}
    }
    return true;
  }catch(e){return false;}
}
const SRCN = {gov:'勞工處', jump:'明報 JUMP', ctgoodjobs:'CTgoodjobs', csb:'公務員事務局', plk:'保良局'};
const $ = id => document.getElementById(id);
const esc = s => String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SAFE_HOSTS=['www1.jobs.gov.hk','jump.mingpao.com','www.ctgoodjobs.hk','csboa2.csb.gov.hk','www.poleungkuk.org.hk'];
const safeUrl=u=>{try{const x=new URL(u);return (x.protocol==='https:'&&SAFE_HOSTS.includes(x.hostname))?x.href:'#';}catch(e){return '#';}};
const TODAY=(()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');})();
const isNew=j=>(j.posted_date||'')>=TODAY;
function card(j){
  return `<div class="card">
  <div class="tags"><span class="tag">${esc(j.level||'護士')}</span>
  <span class="tag src">${esc(j.source_name)}</span>
  ${j.posted_date?`<span class="tag src">刊登 ${esc(j.posted_date)}</span>`:''}
  ${isNew(j)?'<span class="tag new">🆕 今日新職</span>':''}</div>
  <h3><a href="#/job/${j.id}">${esc(j.title||'(冇職稱)')}</a></h3>
  <div class="meta"><span>${esc(j.company||'')}</span></div>
  <div class="meta"><span>📍 ${esc(j.location||'未註明')}</span>
  ${j.employment?`<span>🕒 ${esc(j.employment)}</span>`:''}</div>
  ${j.salary?`<div class="salary">💰 ${esc(j.salary)}</div>`:''}
  </div>`;
}
function renderList(){
  const q=$('q').value.trim().toLowerCase(), lv=$('f-level').value, src=$('f-source').value, nw=$('f-new').checked;
  let list=JOBS.filter(j=>{
    if(lv&&j.level!==lv)return false;
    if(src&&j.source!==src)return false;
    if(nw&&!isNew(j))return false;
    if(q&&!((j.title+' '+j.company+' '+j.location).toLowerCase().includes(q)))return false;
    return true;});
  list.sort((a,b)=>$('f-sort').value==='old'
    ?(a.posted_date||'').localeCompare(b.posted_date||'')
    :(b.posted_date||'').localeCompare(a.posted_date||''));
  $('count').textContent = `共 ${list.length} 個職位`;
  $('empty').style.display=list.length?'none':'block';
  $('list').innerHTML=list.map(card).join('');
  $('listview').style.display='block'; $('detailview').style.display='none';
}
function renderDetail(id){
  const j=JOBS.find(x=>x.id===id);
  if(!j){location.hash='#/';return;}
  const rows=[['刊登日期',j.posted_date||'未註明'],['公司 / 僱主',j.company||'未註明'],
    ['薪金',j.salary||'未註明'],['工作地點',j.location||'未註明'],
    ['僱用形式',j.employment||'未註明'],['資料來源',j.source_name]];
  $('detailview').innerHTML=`<a class="back" href="#/">← 返回職位列表</a>
  <div class="detail">
  <div class="tags"><span class="tag">${esc(j.level||'護士')}</span>
  <span class="tag src">${esc(j.source_name)}</span>
  ${isNew(j)?'<span class="tag new">🆕 今日新職</span>':''}</div>
  <h1>${esc(j.title||'(冇職稱)')}</h1>
  <dl class="kv">${rows.map(r=>`<dt>${r[0]}</dt><dd>${esc(r[1])}</dd>`).join('')}</dl>
  ${j.description?`<h3>職責</h3><pre class="desc">${esc(j.description)}</pre>`:''}
  ${j.requirements?`<h3>要求</h3><pre class="desc">${esc(j.requirements)}</pre>`:''}
  <p><a class="apply" href="${safeUrl(j.apply_url)}" target="_blank" rel="noopener">前往原網站申請 →</a></p>
  </div>`;
  $('listview').style.display='none'; $('detailview').style.display='block';
  window.scrollTo(0,0);
}
function route(){
  const m=location.hash.match(/^#\\/job\\/(.+)$/);
  if(m)renderDetail(m[1]); else renderList();
}
['q','f-level','f-source','f-sort','f-new'].forEach(id=>$(id).addEventListener('input',()=>{location.hash='#/';renderList();}));
window.addEventListener('hashchange',route);
loadLiveJobs().then(()=>{route();});
</script>
<script>
/* Manual refresh button -> dispatch workflow -> poll get-jobs for new updatedAt */
(function(){
  const btn=document.getElementById('refreshBtn'),
        msg=document.getElementById('refreshMsg'),
        lu=document.getElementById('lastUpdated');
  if(!btn)return;
  btn.style.display='inline-flex';btn.hidden=false;
  let cooling=false;
  function cooldown(sec){
    cooling=true;btn.disabled=true;msg.textContent='';
    const iv=setInterval(()=>{
      sec--;
      if(sec<=0){clearInterval(iv);cooling=false;btn.disabled=false;
        btn.textContent='\\u{1F504} 更新職位';msg.textContent='';}
      else{btn.textContent='\\u2705 已更新（'+sec+'s後可再更新）';}
    },1000);
  }
  btn.addEventListener('click',async()=>{
    if(cooling)return;
    btn.disabled=true;msg.textContent='';
    btn.innerHTML='<span class="spinner"></span>更新中\\u2026';
    try{
      const r=await fetch('/.netlify/functions/trigger-update',{method:'POST'});
      let d={};try{d=await r.json();}catch(e){}
      if(r.status===429)throw new Error('操作太頻繁，請10分鐘後再試');
      if(!r.ok||!d.ok)throw new Error(d.error||('觸發失敗（HTTP '+r.status+'）'));
      msg.textContent='已觸發更新，約需5-15分鐘\\u2026';
      const before=(lu&&lu.dataset.ts)||'';
      const t0=Date.now();
      const iv=setInterval(async()=>{
        try{
          const d2=await (await fetch('/.netlify/functions/get-jobs',{cache:'no-store'})).json();
          if(d2&&d2.updatedAt&&d2.updatedAt!==before){
            clearInterval(iv);
            btn.innerHTML='\\u2705 已更新 '+(d2.jobs?d2.jobs.length:'?')+' 個';
            msg.textContent='';
            cooldown(60);
            setTimeout(()=>location.reload(),2000);
          }else if(Date.now()-t0>20*60*1000){
            clearInterval(iv);btn.disabled=false;btn.textContent='\\u{1F504} 更新職位';
            msg.textContent='等候逾時，網站稍後會自動更新';
          }
        }catch(e){/* transient error: keep polling */}
      },10000);
    }catch(e){
      btn.disabled=false;btn.textContent='\\u{1F504} 更新職位';
      msg.textContent='\\u274C '+e.message;
    }
  });
})();
</script>
"""


def build():
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", [])
    updated_iso = payload.get("updated_at", "")
    try:
        updated_dt = datetime.fromisoformat(updated_iso)
        updated = updated_dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        updated = updated_iso or datetime.now(HKT).strftime("%Y-%m-%d %H:%M")

    today = date.today().isoformat()
    new_today = sum(1 for j in jobs if (j.get("posted_date") or "") >= today)
    by_source, by_level = {}, {}
    data = []
    for j in jobs:
        by_source[j["source"]] = by_source.get(j["source"], 0) + 1
        by_level[j.get("level") or "護士"] = by_level.get(j.get("level") or "護士", 0) + 1
        data.append({
            "id": slugify(j["source"], j["external_id"]),
            "title": j.get("title"), "company": j.get("company"), "salary": j.get("salary"),
            "location": j.get("location"), "employment": j.get("employment"),
            "level": j.get("level"), "posted_date": j.get("posted_date"),
            "source": j["source"],
            "source_name": SOURCE_NAMES.get(j["source"], j["source"]),
            "description": j.get("description"), "requirements": j.get("requirements"),
            "apply_url": j.get("apply_url"),
        })
    data.sort(key=lambda j: (j.get("posted_date") or "", j["id"]), reverse=True)
    src_stats = " · ".join(f"{SOURCE_NAMES.get(s, s)} {n}" for s, n in sorted(by_source.items()))
    lvl_stats = " · ".join(f"{lv} {n}" for lv, n in sorted(by_level.items()))
    built_at_iso = datetime.now(HKT).isoformat(timespec="seconds")
    jobs_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    js = JS.replace("/*__JOBS__*/[]", jobs_json)
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant-HK">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>香港護士空缺｜每日更新</title>
<link rel="manifest" href="/assets/manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/icon-192.png">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<meta name="theme-color" content="#0e7c6b">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<style>{CSS}</style>
</head>
<body>
<header><div class="wrap headrow">
<div>
<h1>🩺 香港護士空缺</h1>
<p>每日自動搜羅勞工處、明報 JUMP、CTgoodjobs、公務員事務局、保良局護士職位空缺</p>
</div>
<div class="headright">
<span id="lastUpdated" data-ts="{esc(updated_iso)}">最後更新：{esc(updated)}</span>
<button id="refreshBtn">🔄 更新職位</button>
<span id="refreshMsg"></span>
</div>
</div></header>
<div class="wrap" id="listview">
<div class="stats">
<div class="stat"><b>{len(jobs)}</b><span>有效職位</span></div>
<div class="stat"><b>{new_today}</b><span>今日新增</span></div>
<div class="stat"><b style="font-size:14px">{esc(src_stats)}</b><span>各來源數目</span></div>
<div class="stat"><b style="font-size:14px">{esc(lvl_stats)}</b><span>級別分佈</span></div>
</div>
<div class="toolbar">
<input type="search" id="q" placeholder="搜尋職位、公司、地點…">
<select id="f-level"><option value="">全部級別</option>
<option>RN</option><option>EN</option><option>護士</option></select>
<select id="f-source"><option value="">全部來源</option>
<option value="gov">勞工處</option><option value="jump">明報 JUMP</option>
<option value="ctgoodjobs">CTgoodjobs</option><option value="csb">公務員事務局</option><option value="plk">保良局</option></select>
<select id="f-sort"><option value="new">最新刊登</option><option value="old">最早刊登</option></select>
<label class="chk"><input type="checkbox" id="f-new"> 🆕 只睇今日新職</label>
</div>
<div class="count" id="count"></div>
<div class="grid" id="list"></div>
<div class="empty" id="empty" style="display:none">冇符合條件嘅職位，試下放寬篩選。</div>
<footer>
資料來源：<a href="{SOURCE_URLS['gov']}">勞工處互動就業服務</a> ·
<a href="{SOURCE_URLS['jump']}">明報 JUMP</a> ·
<a href="{SOURCE_URLS['ctgoodjobs']}">CTgoodjobs</a> ·
<a href="{SOURCE_URLS['csb']}">公務員事務局政府職位空缺</a> · <a href="https://www.poleungkuk.org.hk/career">保良局職位空缺</a><br>
本站只作資訊聚合，申請請前往原網站。每日 09:00（香港時間）自動更新。
</footer>
</div>
<div class="wrap" id="detailview" style="display:none"></div>
{js}
</body>
</html>"""
    DIST.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    # Frontend-shaped jobs array for the Blobs pipeline (GitHub workflow pushes
    # this file to Netlify Blobs; get-jobs serves it to the live site).
    (DIST / "jobs.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    VERSION.write_text(json.dumps({
        "built_at": built_at_iso,
        "job_count": len(jobs),
        "sources": payload.get("sources", {}),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    assets_src = ROOT / "assets"
    if assets_src.is_dir():
        shutil.copytree(assets_src, DIST / "assets", dirs_exist_ok=True)
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB, {len(jobs)} jobs)")
    print(f"wrote {VERSION}")


if __name__ == "__main__":
    build()
