"""Vajra Mobile - a phone controller for the desktop Core, served at GET /mobile.

Same-Wi-Fi LAN client per manual v3.0 section 11: pair with the token, submit a
goal or a computer task, watch progress, approve gated actions, stop a run.
Zero install - it is just a page. (A native Flutter build lives in
mobile-android/flutter_app/ for later.)
"""

from __future__ import annotations

MOBILE_HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"/>
<meta name="theme-color" content="#0f1115"/>
<title>Vajra Mobile</title>
<style>
  :root{--bg:#0f1115;--panel:#171a21;--panel2:#1c2029;--border:#262b36;--fg:#e6e8ec;--muted:#8a92a3;--accent:#6ea8fe;--ok:#4ade80;--bad:#f87171;}
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
  header{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--border);padding:12px 16px;display:flex;align-items:center;gap:10px}
  header b{color:var(--accent);letter-spacing:.5px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--bad)}
  .dot.ok{background:var(--ok)}
  main{padding:16px;padding-bottom:80px}
  input,textarea,select,button{font:inherit;width:100%;border-radius:10px;border:1px solid var(--border);background:#0c0e12;color:var(--fg);padding:12px}
  textarea{resize:none}
  button{background:var(--accent);color:#08111f;font-weight:700;border:none;margin-top:10px}
  button.ghost{background:var(--panel2);color:var(--fg);border:1px solid var(--border)}
  .row{display:flex;gap:8px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:12px}
  .muted{color:var(--muted);font-size:13px}
  .tabs{display:flex;gap:6px;position:fixed;bottom:0;left:0;right:0;background:var(--panel);border-top:1px solid var(--border);padding:8px}
  .tabs button{margin:0;background:var(--panel2);color:var(--muted);border:none}
  .tabs button.on{background:var(--accent);color:#08111f}
  .badge{font-size:12px;padding:2px 8px;border-radius:6px;background:var(--border)}
  .badge.passed{background:#14351f;color:var(--ok)} .badge.failed{background:#3a1616;color:var(--bad)}
  .badge.running{background:#16283a;color:var(--accent)}
  .approval{border-color:var(--accent)}
  h3{margin:0 0 8px;font-size:15px}
  .msg{white-space:pre-wrap}
</style></head>
<body>
<header><span id="dot" class="dot"></span><b>VAJRA</b> Mobile <span id="ver" class="muted"></span></header>
<main>
  <section id="pair" class="card">
    <h3>Pair with your PC</h3>
    <input id="url" placeholder="http://192.168.1.20:8760" inputmode="url"/>
    <input id="tok" placeholder="pairing token" style="margin-top:8px"/>
    <button onclick="pair()">Connect</button>
    <div id="pairErr" class="muted" style="color:var(--bad);margin-top:6px"></div>
  </section>

  <section id="viewNew" hidden>
    <div class="card">
      <h3>Computer task</h3>
      <div class="muted">Acts on the PC outside any project. Approvals appear in the Approvals tab.</div>
      <textarea id="cmpText" rows="3" placeholder="e.g. create a folder 'notes' on the Desktop"></textarea>
      <button onclick="runComputer()">Run</button>
    </div>
    <div class="card">
      <h3>Project task</h3>
      <select id="proj"><option value="">— pick a project —</option></select>
      <textarea id="goalText" rows="3" placeholder="e.g. add a /health endpoint and a test" style="margin-top:8px"></textarea>
      <button onclick="runAgent()">Run</button>
    </div>
  </section>

  <section id="viewTasks" hidden></section>
  <section id="viewApprovals" hidden></section>
</main>

<nav class="tabs" id="tabs" hidden>
  <button data-v="New" class="on" onclick="tab('New')">New</button>
  <button data-v="Tasks" onclick="tab('Tasks')">Tasks</button>
  <button data-v="Approvals" onclick="tab('Approvals')">Approvals</button>
</nav>

<script>
const S = { url:"", tok:"", runs:[] };
try{ const s=JSON.parse(localStorage.getItem("vajra.mobile")||"{}"); S.url=s.url||""; S.tok=s.tok||""; }catch(e){}
url.value=S.url; tok.value=S.tok;

function h(){ return {"X-Vajra-Token":S.tok,"Content-Type":"application/json"}; }
async function api(path, opts){ const r=await fetch(S.url+path, opts); if(!r.ok) throw new Error(await r.text()); return r.json(); }

async function pair(){
  S.url=url.value.replace(/\\/+$/,""); S.tok=tok.value.trim(); pairErr.textContent="";
  try{
    const hp=await fetch(S.url+"/api/health"); const j=await hp.json();
    ver.textContent=j.version||"";
    await api("/api/ping",{headers:h()});
    localStorage.setItem("vajra.mobile",JSON.stringify({url:S.url,tok:S.tok}));
    dot.classList.add("ok"); pair.hidden=true; tabs.hidden=false; tab("New");
    loadProjects(); setInterval(poll, 2000);
  }catch(e){ pairErr.textContent="Could not connect / bad token."; }
}

async function loadProjects(){
  try{ const ps=await api("/api/projects",{headers:h()});
    proj.innerHTML='<option value="">— pick a project —</option>'+ps.map(p=>`<option value="${p.root_path}">${p.name}</option>`).join("");
  }catch(e){}
}

async function runComputer(){
  const t=cmpText.value.trim(); if(!t) return; cmpText.value="";
  const r=await api("/api/computer/run",{method:"POST",headers:h(),body:JSON.stringify({instruction:t})});
  S.runs.unshift({kind:"computer",id:r.id,label:t}); tab("Tasks");
}
async function runAgent(){
  const root=proj.value, t=goalText.value.trim(); if(!root||!t){ alert("Pick a project and enter a goal"); return; }
  goalText.value="";
  const r=await api("/api/agent/run",{method:"POST",headers:h(),body:JSON.stringify({goal:t,workspace_root:root})});
  S.runs.unshift({kind:"agent",id:r.id,label:t}); tab("Tasks");
}

async function poll(){
  try{
    const aps=await api("/api/approvals",{headers:h()});
    renderApprovals(aps);
    document.querySelector('[data-v=Approvals]').textContent = "Approvals"+(aps.length?` (${aps.length})`:"");
    for(const run of S.runs){
      try{
        run.state = run.kind==="computer"
          ? await api("/api/computer/runs/"+run.id,{headers:h()})
          : await api("/api/agent/runs/"+run.id,{headers:h()});
      }catch(e){}
    }
    if(cur==="Tasks") renderTasks();
  }catch(e){ dot.classList.remove("ok"); }
}

function renderTasks(){
  viewTasks.innerHTML = S.runs.length? "" : '<div class="muted">No tasks yet.</div>';
  for(const run of S.runs){
    const st=run.state||{}; const status=st.status||"running";
    const tasks=(st.tasks||[]).map(x=>`<div class="muted">• ${x.title} <span class="badge ${x.state}">${x.state}</span></div>`).join("");
    const done=["passed","failed"].includes(status);
    viewTasks.insertAdjacentHTML("beforeend",`<div class="card">
      <div class="row" style="justify-content:space-between"><b>${run.kind}</b><span class="badge ${status}">${status}</span></div>
      <div class="msg" style="margin:6px 0">${run.label}</div>
      ${st.reply?`<div class="muted msg">${st.reply}</div>`:""}
      ${tasks}
      ${st.changed_files&&st.changed_files.length?`<div class="muted">changed: ${st.changed_files.join(", ")}</div>`:""}
      ${(!done&&run.kind==="agent")?`<button class="ghost" onclick="stopRun('${run.id}')">Stop</button>`:""}
    </div>`);
  }
}
async function stopRun(id){ try{ await api("/api/agent/stop",{method:"POST",headers:h(),body:JSON.stringify({run_id:id})}); }catch(e){} }

function renderApprovals(aps){
  viewApprovals.innerHTML = aps.length? "" : '<div class="muted">Nothing waiting.</div>';
  for(const a of aps){
    viewApprovals.insertAdjacentHTML("beforeend",`<div class="card approval">
      <b>${a.tool_name}</b><div class="muted msg">${a.reason||""}</div>
      <div class="muted msg" style="font-size:12px">${JSON.stringify(a.arguments||{})}</div>
      <div class="row">
        <button onclick="approve('${a.id}','approved')">Approve</button>
        <button class="ghost" onclick="approve('${a.id}','rejected')">Reject</button>
      </div>
    </div>`);
  }
}
async function approve(id,verdict){ try{ await api("/api/approvals",{method:"POST",headers:h(),body:JSON.stringify({approval_id:id,verdict})}); poll(); }catch(e){} }

let cur="New";
function tab(v){
  cur=v;
  for(const b of tabs.querySelectorAll("button")) b.classList.toggle("on", b.dataset.v===v);
  viewNew.hidden=v!=="New"; viewTasks.hidden=v!=="Tasks"; viewApprovals.hidden=v!=="Approvals";
  if(v==="Tasks") renderTasks();
}
if(S.url && S.tok) pair();
</script>
</body></html>
"""
