const express = require('express');
const store = require('./store');

const PASSWORD = process.env.ADMIN_PASSWORD;

function createAdminRouter() {
  const router = express.Router();

  // Block everything if no password is configured
  router.use((req, res, next) => {
    if (!PASSWORD) return res.status(503).json({ error: 'Admin not configured' });
    next();
  });

  // Serve the admin page
  router.get('/', (req, res) => {
    res.send(adminHTML());
  });

  // Auth check — password in Authorization header
  function requireAuth(req, res, next) {
    const token = req.headers.authorization;
    if (token !== PASSWORD) return res.status(401).json({ error: 'Unauthorized' });
    next();
  }

  // List namespaces with activity counts
  router.get('/api/namespaces', requireAuth, async (req, res) => {
    try {
      const rows = await store.getActiveNamespaces();
      res.json(rows);
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  // Get logs for a namespace
  router.get('/api/logs/:namespace', requireAuth, async (req, res) => {
    try {
      const rows = await store.getLogsByNamespace(req.params.namespace, 200);
      res.json(rows);
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  return router;
}

function adminHTML() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BotBeam Admin</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 24px; }
  h1 { font-size: 18px; margin-bottom: 20px; color: #fff; }
  h2 { font-size: 14px; margin-bottom: 12px; color: #aaa; }

  #login { max-width: 300px; margin: 100px auto; }
  #login input { width: 100%; padding: 10px; background: #1a1a1a; border: 1px solid #333; color: #fff; border-radius: 4px; font-size: 14px; }
  #login button { margin-top: 8px; width: 100%; padding: 10px; background: #2563eb; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
  #login .error { color: #f87171; font-size: 12px; margin-top: 8px; }

  #app { display: none; }
  .columns { display: flex; gap: 24px; }
  .col-ns { width: 300px; flex-shrink: 0; }
  .col-logs { flex: 1; min-width: 0; }

  .ns-list { list-style: none; }
  .ns-list li { padding: 8px 12px; cursor: pointer; border-radius: 4px; font-size: 13px; display: flex; justify-content: space-between; }
  .ns-list li:hover { background: #1a1a1a; }
  .ns-list li.active { background: #1e3a5f; }
  .ns-list .count { color: #666; font-size: 12px; }
  .ns-list .time { color: #555; font-size: 11px; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 6px 10px; border-bottom: 1px solid #333; color: #888; font-weight: 500; }
  td { padding: 6px 10px; border-bottom: 1px solid #1a1a1a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
  tr:hover td { background: #111; }
  .action { color: #60a5fa; }
  .time-col { color: #666; }
</style>
</head>
<body>

<div id="login">
  <h1>BotBeam Admin</h1>
  <input type="password" id="pw" placeholder="Password" autofocus>
  <button onclick="doLogin()">Log in</button>
  <div class="error" id="login-error"></div>
</div>

<div id="app">
  <h1>BotBeam Admin</h1>
  <div class="columns">
    <div class="col-ns">
      <h2>Namespaces</h2>
      <ul class="ns-list" id="ns-list"></ul>
    </div>
    <div class="col-logs">
      <h2 id="logs-heading">Select a namespace</h2>
      <table id="logs-table" style="display:none">
        <thead><tr><th>Time</th><th>Action</th><th>Device</th><th>Type</th><th>IP</th></tr></thead>
        <tbody id="logs-body"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
let token = localStorage.getItem('botbeam-admin-token') || '';

if (token) tryLoad();

document.getElementById('pw').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

async function doLogin() {
  token = document.getElementById('pw').value;
  const ok = await tryLoad();
  if (ok) {
    localStorage.setItem('botbeam-admin-token', token);
  } else {
    document.getElementById('login-error').textContent = 'Wrong password';
  }
}

async function tryLoad() {
  try {
    const res = await fetch('/admin/api/namespaces', { headers: { Authorization: token } });
    if (!res.ok) return false;
    const data = await res.json();
    document.getElementById('login').style.display = 'none';
    document.getElementById('app').style.display = 'block';
    renderNamespaces(data);
    return true;
  } catch { return false; }
}

function renderNamespaces(list) {
  const ul = document.getElementById('ns-list');
  ul.innerHTML = '';
  for (const ns of list) {
    const li = document.createElement('li');
    const ago = timeAgo(ns.lastActivity);
    li.innerHTML = '<span>' + ns.namespace + ' <span class="count">(' + ns.count + ')</span></span><span class="time">' + ago + '</span>';
    li.onclick = () => {
      ul.querySelectorAll('li').forEach(l => l.classList.remove('active'));
      li.classList.add('active');
      loadLogs(ns.namespace);
    };
    ul.appendChild(li);
  }
}

async function loadLogs(namespace) {
  document.getElementById('logs-heading').textContent = namespace;
  const res = await fetch('/admin/api/logs/' + namespace, { headers: { Authorization: token } });
  const rows = await res.json();
  const tbody = document.getElementById('logs-body');
  tbody.innerHTML = '';
  document.getElementById('logs-table').style.display = '';
  for (const r of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td class="time-col">' + new Date(r.createdAt).toLocaleString() + '</td>' +
      '<td class="action">' + esc(r.action) + '</td>' +
      '<td>' + esc(r.device || '') + '</td>' +
      '<td>' + esc(r.contentType || '') + '</td>' +
      '<td>' + esc(r.ip || '') + '</td>';
    tbody.appendChild(tr);
  }
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  return Math.floor(hrs / 24) + 'd ago';
}
</script>
</body>
</html>`;
}

module.exports = { createAdminRouter };
