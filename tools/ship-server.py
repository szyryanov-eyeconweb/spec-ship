#!/usr/bin/env python3
"""spec-ship server — живой дашборд по pipeline и roadmap проекта.

Две вкладки: Pipeline — список фич/багов (.ship/pipeline/*/), клик — задачи,
зависимости, acceptance coverage. Roadmap — список эпиков (.ship/roadmap/*/),
клик — тикеты эпика, зависимости, decisions/not_yet_specified/out_of_scope.
Без пересборки: каждый запрос читает файлы заново, F5 = свежие данные.

Только stdlib (http.server). Слушает localhost, ничего никуда не отправляет.

Запуск:
    tools/ship-server.py                      # проект = cwd, порт 8765
    tools/ship-server.py --project /path
    tools/ship-server.py --port 9000 --open
"""
from __future__ import annotations
import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ship_pipeline_data import (  # noqa: E402
    load_pipeline, collect, list_pipelines, load_epic, list_epics,
)

INDEX_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>spec-ship pipeline</title>
<style>
:root{
  --bg:#FAFAF8; --surface:#fff; --border:#E4E2DC; --text:#1A1A18; --text-dim:#6B6A63; --text-faint:#9A988F;
  --accent:#0E4F4A; --accent-soft:#E4F0EE;
  --done:#2F7D4F; --done-soft:#E5F3EA;
  --blocked:#B33F3F; --blocked-soft:#FBEAE8;
  --pending:#9A7B12; --pending-soft:#FBF3DE;
  --critical:#8A2A6B; --critical-soft:#F6E7F1;
  --routine-soft:#EFEDE6; --logic-soft:#E4EAF6;
  color-scheme: light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#171715; --surface:#201F1C; --border:#34332E; --text:#EDECE6; --text-dim:#A6A49A; --text-faint:#726F65;
    --accent:#5FBDB4; --accent-soft:#1B3532;
    --done:#6FCB8F; --done-soft:#1C3327;
    --blocked:#E8837A; --blocked-soft:#3A211E;
    --pending:#E3C05A; --pending-soft:#3A3016;
    --critical:#D98BC2; --critical-soft:#3A2334;
    --routine-soft:#2A2925; --logic-soft:#232A38;
    color-scheme: dark;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:960px;margin:0 auto;padding:24px 16px 48px}
.mono{font-family:"JetBrains Mono","SF Mono",monospace}
a{color:inherit;text-decoration:none}

/* top bar */
.topbar-row{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:22px}
.topbar{display:flex;align-items:center;gap:10px;cursor:pointer}
.topbar .logo{width:26px;height:26px;border-radius:7px;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;flex-shrink:0}
.topbar h1{font-size:16px;font-weight:700;margin:0}
.topbar .sub{font-size:11.5px;color:var(--text-faint)}
.tabs{display:flex;gap:4px;background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:3px}
.tab{font-size:12.5px;font-weight:600;padding:5px 12px;border-radius:6px;color:var(--text-dim);cursor:pointer}
.tab:hover{color:var(--text)}
.tab.active{background:var(--accent);color:#fff}

/* list view */
.list-stats{display:flex;gap:16px;font-size:12px;color:var(--text-dim);margin-bottom:16px}
.list-stats b{color:var(--text);font-variant-numeric:tabular-nums}
.cards{display:flex;flex-direction:column;gap:8px}
.pcard{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:13px 15px;cursor:pointer;transition:border-color .12s}
.pcard:hover{border-color:var(--accent)}
.pcard-head{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
.pcard-title{font-size:14px;font-weight:600;flex:1;min-width:0}
.pcard-slug{font-size:10.5px;color:var(--text-faint)}
.pcard-meta{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:11px;color:var(--text-dim)}
.pcard-bar{height:5px;border-radius:3px;background:var(--border);overflow:hidden;margin-top:8px;display:flex}
.pcard-bar .seg{height:100%}
.pcard-bar .seg.done{background:var(--done)}
.badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:20px;font-size:10.5px;font-weight:600}
.badge.frozen,.badge.approved{background:var(--accent-soft);color:var(--accent)}
.badge.proposal,.badge.draft{background:var(--pending-soft);color:var(--pending)}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.filter-chip{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:20px;border:1px solid var(--border);background:var(--surface);color:var(--text-dim);cursor:pointer;display:inline-flex;align-items:center;gap:5px}
.filter-chip:hover{border-color:var(--accent)}
.filter-chip.active{background:var(--accent);border-color:var(--accent);color:#fff}
.filter-chip .cnt{font-variant-numeric:tabular-nums;opacity:.75}
.chip{font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:5px}
.chip.critical{background:var(--critical-soft);color:var(--critical)}
.chip.blocked{background:var(--blocked-soft);color:var(--blocked)}
.chip.diagnosis{background:var(--blocked-soft);color:var(--blocked)}
.empty{padding:40px 0;text-align:center;color:var(--text-faint);font-size:13px}

/* detail view (mirrors ship-dashboard.py output) */
.back{display:inline-flex;align-items:center;gap:5px;font-size:12.5px;color:var(--text-dim);margin-bottom:16px;cursor:pointer}
.back:hover{color:var(--accent)}
header.detail{margin-bottom:22px}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-faint);margin-bottom:6px}
h2.title{font-size:21px;font-weight:700;margin:0 0 8px;text-wrap:balance}
.subtitle{font-size:13px;color:var(--text-dim);margin:0 0 10px;max-width:70ch}
.meta-row{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:12.5px;color:var(--text-dim)}
.meta-row .mono{color:var(--text)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0 28px}
@media (max-width:640px){.stats{grid-template-columns:repeat(2,1fr)}}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.stat .n{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.stat .l{font-size:11.5px;color:var(--text-dim);margin-top:2px}
.stat.done .n{color:var(--done)}
.stat.pending .n{color:var(--pending)}
.stat.critical .n{color:var(--critical)}
.progress-track{height:8px;border-radius:5px;background:var(--border);overflow:hidden;display:flex;margin-bottom:6px}
.progress-track .seg{height:100%}
.progress-track .seg.done{background:var(--done)}
.progress-track .seg.pending{background:var(--border)}
.progress-legend{display:flex;gap:16px;font-size:11.5px;color:var(--text-dim);margin-top:6px;margin-bottom:28px}
.progress-legend span{display:inline-flex;align-items:center;gap:5px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
section{margin-bottom:32px}
h3.sec{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--text-dim);margin:0 0 12px}
.tasks{display:flex;flex-direction:column;gap:6px}
.task{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:11px 13px;display:grid;grid-template-columns:auto 1fr auto;gap:4px 12px;align-items:center}
.task .id{font-size:11px;color:var(--text-faint)}
.task .ttitle{grid-column:1/3;font-size:13px;font-weight:500}
.task .status-pill{grid-row:1/3;justify-self:end;align-self:start;display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:600;white-space:nowrap}
.status-pill.built{background:var(--done-soft);color:var(--done)}
.status-pill.blocked{background:var(--blocked-soft);color:var(--blocked)}
.status-pill.pending{background:var(--pending-soft);color:var(--pending)}
.task .tags{grid-column:1/3;display:flex;flex-wrap:wrap;gap:5px;margin-top:2px}
.tag{font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:5px}
.tag.tz-ROUTINE{background:var(--routine-soft);color:var(--text-dim)}
.tag.tz-LOGIC{background:var(--logic-soft);color:#3C5A9A}
.tag.tz-CRITICAL{background:var(--critical-soft);color:var(--critical)}
.tag.risk-low{background:var(--done-soft);color:var(--done)}
.tag.risk-medium{background:var(--pending-soft);color:var(--pending)}
.tag.risk-high{background:var(--blocked-soft);color:var(--blocked)}
.tag.dep{background:var(--bg);border:1px solid var(--border);color:var(--text-faint)}
.tag.dep.unmet{color:var(--blocked);border-color:var(--blocked)}
.tag.cov{background:var(--accent-soft);color:var(--accent)}
.tag.rev-ok{background:var(--done-soft);color:var(--done)}
.task .note{grid-column:1/3;font-size:11.5px;color:var(--text-faint);margin-top:3px}
.cov{display:flex;flex-direction:column;gap:8px}
.cov-row{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:11px 13px;display:flex;gap:12px;align-items:flex-start}
.cov-row.gap{border-color:var(--blocked);background:var(--blocked-soft)}
.cov-id{flex-shrink:0;width:52px;font-size:11.5px;font-weight:700;color:var(--text-dim)}
.cov-row.gap .cov-id{color:var(--blocked)}
.cov-body{flex:1;min-width:0}
.cov-scenario{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--text-faint);margin-bottom:3px}
.cov-then{font-size:12.5px;color:var(--text-dim)}
.cov-covered{flex-shrink:0;display:flex;flex-direction:column;gap:3px;align-items:flex-end}
.cov-covered .mono{font-size:10.5px;color:var(--text-faint)}
.cov-covered .none{font-size:11px;font-weight:700;color:var(--blocked)}
footer{font-size:11px;color:var(--text-faint);border-top:1px solid var(--border);padding-top:14px;margin-top:8px}

/* roadmap: epic cards */
.ecard{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:13px 15px;cursor:pointer;transition:border-color .12s}
.ecard:hover{border-color:var(--accent)}
.ecard-head{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
.ecard-title{font-size:14px;font-weight:600;flex:1;min-width:0}
.ecard-dest{font-size:12px;color:var(--text-dim);margin-bottom:8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ecard-bar{height:5px;border-radius:3px;background:var(--border);overflow:hidden;display:flex}
.ecard-bar .seg.done{background:var(--accent);height:100%}

/* roadmap: ticket rows */
.tickets{display:flex;flex-direction:column;gap:6px}
.ticket{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:11px 13px;display:grid;grid-template-columns:auto 1fr auto;gap:4px 12px;align-items:center}
.ticket .id{font-size:11px;color:var(--text-faint)}
.ticket .ttitle{grid-column:1/3;font-size:13px;font-weight:500}
.ticket .status-pill{grid-row:1/3;justify-self:end;align-self:start;display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:600;white-space:nowrap}
.status-pill.closed{background:var(--done-soft);color:var(--done)}
.status-pill.open-blocked{background:var(--blocked-soft);color:var(--blocked)}
.status-pill.open-ready{background:var(--pending-soft);color:var(--pending)}
.ticket .tags{grid-column:1/3;display:flex;flex-wrap:wrap;gap:5px;margin-top:2px}
.tag.type{background:var(--routine-soft);color:var(--text-dim)}
.tag.hitl{background:var(--logic-soft);color:#3C5A9A}
.tag.outcome-ready_for_run{background:var(--accent-soft);color:var(--accent)}
.tag.outcome-out_of_scope{background:var(--blocked-soft);color:var(--blocked)}
.tag.outcome-decision,.tag.outcome-done{background:var(--done-soft);color:var(--done)}
.ticket .qtext{grid-column:1/3;font-size:12px;color:var(--text-dim);margin-top:3px}
.ticket .rtext{grid-column:1/3;font-size:11.5px;color:var(--text-faint);margin-top:3px;border-left:2px solid var(--border);padding-left:8px}

/* roadmap: map side sections */
.mapinfo{display:flex;flex-direction:column;gap:8px}
.mapinfo-item{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 13px;font-size:12.5px;color:var(--text-dim)}
.mapinfo-item.scope-out{border-color:var(--blocked);background:var(--blocked-soft);color:var(--text)}
.mapinfo-item .why{color:var(--text-faint);font-size:11.5px;margin-top:3px}
.destination-box{font-size:13px;color:var(--text-dim);background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:20px}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar-row">
    <div class="topbar" onclick="location.hash=currentSection()">
      <div class="logo">S</div>
      <h1>spec-ship</h1>
      <span class="sub" id="topSub"></span>
    </div>
    <div class="tabs">
      <span class="tab" data-section="pipeline" onclick="location.hash='pipeline'">Pipeline</span>
      <span class="tab" data-section="roadmap" onclick="location.hash='roadmap'">Roadmap</span>
    </div>
  </div>
  <div id="app"></div>
</div>
<script>
const STATUS_LABEL = {built:"собрано", blocked:"заблокировано", pending:"готово к сборке"};

async function fetchJSON(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

function esc(s){
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function loadActiveStatuses(){
  try{
    const raw = sessionStorage.getItem('ship-status-filter');
    if(raw) return new Set(JSON.parse(raw));
  }catch(e){}
  return new Set();
}
function saveActiveStatuses(set){
  try{ sessionStorage.setItem('ship-status-filter', JSON.stringify([...set])); }catch(e){}
}
let activeStatuses = loadActiveStatuses();

function renderCards(items){
  return items.map(p=>{
    const pct = p.task_count ? Math.round(100*p.built_count/p.task_count) : 0;
    const chips = [];
    if(p.root_type==='diagnosis') chips.push('<span class="chip diagnosis">bug</span>');
    if(p.critical_count>0) chips.push(`<span class="chip critical">${p.critical_count} CRITICAL</span>`);
    if(p.blocked_count>0) chips.push(`<span class="chip blocked">${p.blocked_count} заблокировано</span>`);
    return `
    <div class="pcard" onclick="location.hash='pipeline/${encodeURIComponent(p.slug)}'">
      <div class="pcard-head">
        <span class="pcard-title">${esc(p.title)}</span>
        <span class="badge ${esc(p.status)}">${esc(p.status)}</span>
      </div>
      <div class="pcard-meta">
        <span class="mono pcard-slug">${esc(p.slug)}</span>
        <span>${p.built_count}/${p.task_count} задач</span>
        ${chips.join('')}
      </div>
      <div class="pcard-bar"><div class="seg done" style="width:${pct}%"></div></div>
    </div>`;
  }).join('');
}

function toggleStatus(status){
  if(activeStatuses.has(status)) activeStatuses.delete(status);
  else activeStatuses.add(status);
  saveActiveStatuses(activeStatuses);
  route();
}

async function renderList(){
  document.getElementById('topSub').textContent = '';
  const app = document.getElementById('app');
  app.innerHTML = '<div class="empty">загрузка…</div>';
  let items;
  try{ items = await fetchJSON('/api/projects'); }
  catch(e){ app.innerHTML = `<div class="empty">Ошибка: ${esc(e.message)}</div>`; return; }

  if(items.length===0){
    app.innerHTML = '<div class="empty">В .ship/pipeline/ пока нет ни одной задачи.</div>';
    return;
  }

  // статусы, которых реально нет в данных, из фильтра не выкидываем молча —
  // просто они не найдут совпадений; но чипы рисуем только по факту наличия
  const statusCounts = new Map();
  items.forEach(p=>statusCounts.set(p.status, (statusCounts.get(p.status)||0)+1));
  const statuses = [...statusCounts.keys()].sort();

  const filtered = activeStatuses.size
    ? items.filter(p=>activeStatuses.has(p.status))
    : items;

  const totalTasks = items.reduce((s,p)=>s+p.task_count,0);
  const totalBuilt = items.reduce((s,p)=>s+p.built_count,0);
  document.getElementById('topSub').textContent = `${items.length} pipeline · ${totalBuilt}/${totalTasks} задач собрано`;

  const filterHtml = `
    <div class="filters">
      ${statuses.map(s=>`
        <span class="filter-chip ${activeStatuses.has(s)?'active':''}" onclick="toggleStatus('${esc(s)}')">
          ${esc(s)} <span class="cnt">${statusCounts.get(s)}</span>
        </span>`).join('')}
      ${activeStatuses.size ? `<span class="filter-chip" onclick="activeStatuses.clear();saveActiveStatuses(activeStatuses);route()">&times; сбросить</span>` : ''}
    </div>
  `;

  const cardsHtml = filtered.length
    ? renderCards(filtered)
    : '<div class="empty">Ничего не подходит под выбранные статусы.</div>';

  app.innerHTML = `
    ${filterHtml}
    <div class="cards">${cardsHtml}</div>
  `;
}

async function renderDetail(slug){
  const app = document.getElementById('app');
  app.innerHTML = '<div class="empty">загрузка…</div>';
  let data;
  try{ data = await fetchJSON('/api/pipeline/' + encodeURIComponent(slug)); }
  catch(e){ app.innerHTML = `<div class="empty">Ошибка: ${esc(e.message)}<br><span class="back" onclick="location.hash='pipeline'">&larr; назад к списку</span></div>`; return; }

  const meta = data.meta || {};
  const tasks = data.tasks || [];
  const acceptance = data.acceptance || [];
  const counts = data.counts || {};
  const byId = Object.fromEntries(tasks.map(t=>[t.id,t]));
  const coveredSet = new Set(tasks.flatMap(t=>t.covers));
  const rootLabel = {'business-doc':'business doc','diagnosis':'diagnosis'}[meta.root_type] || 'pipeline';

  const statsHtml = `
    <div class="stat done"><div class="n">${tasks.filter(t=>t.built).length}/${tasks.length}</div><div class="l">задач собрано</div></div>
    <div class="stat"><div class="n mono">${tasks.filter(t=>t.tz==='CRITICAL').length}</div><div class="l">CRITICAL зона</div></div>
    <div class="stat pending"><div class="n">${tasks.filter(t=>t.status==='blocked').length}</div><div class="l">заблокировано</div></div>
    <div class="stat critical"><div class="n">${Math.max(0, acceptance.length - coveredSet.size)}</div><div class="l">AC без покрытия</div></div>
  `;

  const trackHtml = tasks.length
    ? tasks.map(t=>`<div class="seg ${t.built?'done':'pending'}" style="width:${100/tasks.length}%"></div>`).join('')
    : '';

  const tasksHtml = tasks.length ? tasks.map(t=>{
    const depTags = t.depends_on.map(d=>{
      const unmet = !(byId[d] && byId[d].built);
      return `<span class="tag dep${unmet?' unmet':''}">${unmet?'&#9940;':'&#10003;'} ${esc(d)}</span>`;
    }).join('');
    const covTags = t.covers.map(c=>`<span class="tag cov">covers ${esc(c)}</span>`).join('');
    const revTag = t.reviewed ? '<span class="tag rev-ok">&#10003; reviewed</span>' : '';
    return `
    <div class="task">
      <span class="id mono">${esc(t.id)}</span>
      <span class="status-pill ${t.status}">${t.status==='built'?'&#10003;':t.status==='blocked'?'&#9940;':'&#9675;'} ${STATUS_LABEL[t.status]}</span>
      <span class="ttitle">${esc(t.title)}</span>
      <span class="tags">
        <span class="tag tz-${esc(t.tz)}">${esc(t.tz)}</span>
        <span class="tag risk-${esc(t.risk)}">risk: ${esc(t.risk)}</span>
        ${depTags}${covTags}${revTag}
      </span>
      <span class="note">${esc(t.note||'')}</span>
    </div>`;
  }).join('') : '<div class="empty">Нет task-spec в этой pipeline-папке.</div>';

  const covHtml = acceptance.length ? acceptance.map(ac=>{
    const owners = tasks.filter(t=>t.covers.includes(ac.id)).map(t=>t.id);
    const gap = owners.length===0;
    return `
    <div class="cov-row ${gap?'gap':''}">
      <span class="cov-id mono">${esc(ac.id)}</span>
      <span class="cov-body">
        <div class="cov-scenario">${esc(ac.scenario)}</div>
        <div class="cov-then">${esc(ac.then)}</div>
      </span>
      <span class="cov-covered">
        ${gap ? '<span class="none">нет владельца</span>' : owners.map(o=>`<span class="mono">${esc(o)}</span>`).join('')}
      </span>
    </div>`;
  }).join('') : '<div class="empty">Нет acceptance_criteria.</div>';

  document.getElementById('topSub').textContent = slug;
  app.innerHTML = `
    <span class="back" onclick="location.hash='pipeline'">&larr; ко всем задачам</span>
    <header class="detail">
      <div class="eyebrow">spec-ship &middot; ${esc(rootLabel)}</div>
      <h2 class="title">${esc(meta.title||slug)}</h2>
      ${meta.subtitle ? `<p class="subtitle">${esc(meta.subtitle)}</p>` : ''}
      <div class="meta-row">
        <span class="badge ${esc(meta.status)}">${esc(meta.status||'—')}</span>
        <span>id <span class="mono">${esc(meta.id||slug)}</span></span>
        <span>создан <span class="mono">${esc(meta.created_at||'—')}</span></span>
        <span><span class="mono">${meta.open_questions||0}</span> open questions</span>
      </div>
    </header>
    <div class="stats">${statsHtml}</div>
    <div class="progress-track">${trackHtml}</div>
    <div class="progress-legend">
      <span><span class="dot" style="background:var(--done)"></span>собрано</span>
      <span><span class="dot" style="background:var(--border)"></span>в очереди</span>
    </div>
    <section>
      <h3 class="sec">Задачи &middot; dependency chain</h3>
      <div class="tasks">${tasksHtml}</div>
    </section>
    <section>
      <h3 class="sec">Покрытие acceptance criteria</h3>
      <div class="cov">${covHtml}</div>
    </section>
    <footer>${esc(slug)} &middot; ${tasks.length} task-spec &middot; ${tasks.filter(t=>t.built).length} build-report &middot; ${counts.adr_entries||0} adr-entry &middot; ${counts.surveys||0} survey</footer>
  `;
}

async function renderRoadmapList(){
  document.getElementById('topSub').textContent = '';
  const app = document.getElementById('app');
  app.innerHTML = '<div class="empty">загрузка…</div>';
  let items;
  try{ items = await fetchJSON('/api/epics'); }
  catch(e){ app.innerHTML = `<div class="empty">Ошибка: ${esc(e.message)}</div>`; return; }

  if(items.length===0){
    app.innerHTML = '<div class="empty">В .ship/roadmap/ пока нет ни одного эпика.</div>';
    return;
  }

  const totalTickets = items.reduce((s,e)=>s+e.ticket_count,0);
  const totalClosed = items.reduce((s,e)=>s+e.closed_count,0);
  document.getElementById('topSub').textContent = `${items.length} эпиков · ${totalClosed}/${totalTickets} тикетов закрыто`;

  const cards = items.map(e=>{
    const pct = e.ticket_count ? Math.round(100*e.closed_count/e.ticket_count) : 0;
    const chips = [];
    if(e.hitl_open_count>0) chips.push(`<span class="chip blocked">${e.hitl_open_count} ждёт человека</span>`);
    if(e.ready_for_run_count>0) chips.push(`<span class="chip critical" style="background:var(--accent-soft);color:var(--accent)">${e.ready_for_run_count} ready_for_run</span>`);
    if(e.not_yet_specified_count>0) chips.push(`<span class="chip">${e.not_yet_specified_count} в тумане</span>`);
    return `
    <div class="ecard" onclick="location.hash='roadmap/${encodeURIComponent(e.slug)}'">
      <div class="ecard-head">
        <span class="ecard-title">${esc(e.epic)}</span>
        <span class="mono" style="font-size:11px;color:var(--text-faint)">${e.closed_count}/${e.ticket_count}</span>
      </div>
      <div class="ecard-dest">${esc(e.destination)}</div>
      <div class="pcard-meta" style="margin-bottom:8px">${chips.join('')}</div>
      <div class="ecard-bar"><div class="seg done" style="width:${pct}%"></div></div>
    </div>`;
  }).join('');

  app.innerHTML = `<div class="cards">${cards}</div>`;
}

async function renderEpicDetail(slug){
  const app = document.getElementById('app');
  app.innerHTML = '<div class="empty">загрузка…</div>';
  let e;
  try{ e = await fetchJSON('/api/epic/' + encodeURIComponent(slug)); }
  catch(err){ app.innerHTML = `<div class="empty">Ошибка: ${esc(err.message)}<br><span class="back" onclick="location.hash='roadmap'">&larr; назад к эпикам</span></div>`; return; }

  const tickets = e.tickets || [];
  const closed = tickets.filter(t=>t.status==='closed').length;
  const openHitl = tickets.filter(t=>t.status==='open' && t.hitl).length;
  const blocked = tickets.filter(t=>t.blocked).length;
  const notSpecified = e.not_yet_specified || [];

  document.getElementById('topSub').textContent = slug;

  const statsHtml = `
    <div class="stat done"><div class="n">${closed}/${tickets.length}</div><div class="l">тикетов закрыто</div></div>
    <div class="stat pending"><div class="n">${openHitl}</div><div class="l">ждут человека</div></div>
    <div class="stat"><div class="n mono">${blocked}</div><div class="l">заблокировано</div></div>
    <div class="stat critical"><div class="n">${notSpecified.length}</div><div class="l">в тумане</div></div>
  `;

  const ticketsHtml = tickets.length ? tickets.map(t=>{
    let pillClass, pillLabel;
    if(t.status==='closed'){ pillClass='closed'; pillLabel='закрыт'; }
    else if(t.blocked){ pillClass='open-blocked'; pillLabel='заблокирован'; }
    else { pillClass='open-ready'; pillLabel='открыт'; }
    const depTags = t.depends_on.map(d=>{
      const dep = tickets.find(x=>x.id===d);
      const unmet = !(dep && dep.status==='closed');
      return `<span class="tag dep${unmet?' unmet':''}">${unmet?'&#9940;':'&#10003;'} ${esc(d)}</span>`;
    }).join('');
    const typeTag = `<span class="tag type">${esc(t.type)}</span>`;
    const hitlTag = t.hitl ? '<span class="tag hitl">HITL</span>' : '';
    const outcomeTag = t.outcome ? `<span class="tag outcome-${esc(t.outcome)}">${esc(t.outcome)}</span>` : '';
    const claimTag = t.claimed_by ? `<span class="tag dep">&#128100; ${esc(t.claimed_by)}</span>` : '';
    return `
    <div class="ticket">
      <span class="id mono">${esc(t.id)}</span>
      <span class="status-pill ${pillClass}">${STATUS_ICON[pillClass]||''} ${pillLabel}</span>
      <span class="ttitle">${esc(t.title)}</span>
      <span class="tags">${typeTag}${hitlTag}${outcomeTag}${claimTag}${depTags}</span>
      <span class="qtext"><b>?</b> ${esc(t.question)}</span>
      ${t.resolution ? `<span class="rtext">${esc(t.resolution)}</span>` : ''}
    </div>`;
  }).join('') : '<div class="empty">Нет тикетов в этом эпике.</div>';

  const outOfScope = e.out_of_scope || [];
  const sideHtml = `
    <section>
      <h3 class="sec">Не сформулировано (туман)</h3>
      <div class="mapinfo">
        ${notSpecified.length ? notSpecified.map(n=>`<div class="mapinfo-item">${esc(n)}</div>`).join('') : '<div class="empty">Пусто.</div>'}
      </div>
    </section>
    <section>
      <h3 class="sec">Вне скоупа</h3>
      <div class="mapinfo">
        ${outOfScope.length ? outOfScope.map(o=>`<div class="mapinfo-item scope-out">${esc(o.gist||'')}${o.why?`<div class="why">${esc(o.why)}</div>`:''}</div>`).join('') : '<div class="empty">Пусто.</div>'}
      </div>
    </section>
  `;

  app.innerHTML = `
    <span class="back" onclick="location.hash='roadmap'">&larr; ко всем эпикам</span>
    <header class="detail">
      <div class="eyebrow">spec-ship &middot; roadmap epic</div>
      <h2 class="title">${esc(e.epic)}</h2>
      <div class="destination-box">${esc(e.destination)}</div>
      <div class="meta-row">
        <span>создан <span class="mono">${esc(e.created_at||'—')}</span></span>
        <span>${esc(e.created_by||'')}</span>
      </div>
    </header>
    <div class="stats">${statsHtml}</div>
    <section>
      <h3 class="sec">Тикеты</h3>
      <div class="tickets">${ticketsHtml}</div>
    </section>
    ${sideHtml}
    <footer>${esc(slug)} &middot; ${tickets.length} тикетов</footer>
  `;
}

function currentSection(){
  const h = location.hash.slice(1);
  return h.startsWith('roadmap') ? 'roadmap' : 'pipeline';
}

function updateTabs(){
  const section = currentSection();
  document.querySelectorAll('.tab').forEach(el=>{
    el.classList.toggle('active', el.dataset.section===section);
  });
}

const STATUS_ICON = {closed:'&#10003;', 'open-blocked':'&#9940;', 'open-ready':'&#9675;'};

function route(){
  updateTabs();
  const raw = decodeURIComponent(location.hash.slice(1));
  if(!raw || raw==='pipeline'){ renderList(); return; }
  if(raw==='roadmap'){ renderRoadmapList(); return; }
  if(raw.startsWith('roadmap/')){ renderEpicDetail(raw.slice('roadmap/'.length)); return; }
  // bare slug (no "pipeline/" prefix) -> treat as pipeline detail for back-compat
  const slug = raw.startsWith('pipeline/') ? raw.slice('pipeline/'.length) : raw;
  renderDetail(slug);
}
window.addEventListener('hashchange', route);
route();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    project: Path = Path.cwd()

    def log_message(self, fmt, *args):  # quieter default logging
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._html(INDEX_HTML)
            return

        if path == "/api/projects":
            self._json(list_pipelines(self.project))
            return

        if path.startswith("/api/pipeline/"):
            slug = path[len("/api/pipeline/"):]
            from urllib.parse import unquote
            slug = unquote(slug)
            pipeline_dir = self.project / ".ship" / "pipeline" / slug
            if not pipeline_dir.is_dir():
                self._json({"error": f"нет такой pipeline-папки: {slug}"}, status=404)
                return
            buckets = load_pipeline(pipeline_dir)
            if not buckets:
                self._json({"error": f"в {slug} не найдено артефактов с $schema"}, status=404)
                return
            self._json(collect(buckets))
            return

        if path == "/api/epics":
            self._json(list_epics(self.project))
            return

        if path.startswith("/api/epic/"):
            slug = path[len("/api/epic/"):]
            from urllib.parse import unquote
            slug = unquote(slug)
            epic_dir = self.project / ".ship" / "roadmap" / slug
            if not epic_dir.is_dir():
                self._json({"error": f"нет такого эпика: {slug}"}, status=404)
                return
            epic = load_epic(epic_dir)
            if epic is None:
                self._json({"error": f"в {slug} нет MAP.json"}, status=404)
                return
            self._json(epic)
            return

        self._json({"error": "not found"}, status=404)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="корень проекта (по умолчанию — cwd)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="открыть в браузере после старта")
    args = ap.parse_args()

    project = args.project.resolve()
    if not (project / ".ship" / "pipeline").is_dir():
        print(f"внимание: {project}/.ship/pipeline не найден — список будет пустым", file=sys.stderr)

    Handler.project = project
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"spec-ship dashboard: {url}  (проект: {project})")
    print("Ctrl+C для остановки")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
