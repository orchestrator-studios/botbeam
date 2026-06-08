require('dotenv').config();

const http = require('http');
const path = require('path');
const express = require('express');
const { initDB } = require('./db');
const { createWSServer } = require('./websocket');
const { createRouter: createAPIRouter } = require('./routes');
const { createAuthRouter, requireAuth } = require('./auth');
const { logAPI, normalizeIP, getIP } = require('./log');
const { createLogger, generateRequestId } = require('./logger');
const { createAdminRouter } = require('./admin');
const store = require('./store');

const fs = require('fs');

const httpLog = createLogger('http');
const PORT = process.env.PORT || 4888;
const VERSION = fs.readFileSync(path.join(__dirname, '..', 'VERSION'), 'utf8').trim();
const app = express();
const server = http.createServer(app);

const { broadcast, broadcastGlobal } = createWSServer(server);

// Middleware
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    res.setHeader('Access-Control-Allow-Credentials', 'true');
  }
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});
app.use(express.json());

// Request logging
app.use((req, res, next) => {
  if (req.path === '/health') return next();
  req.id = generateRequestId();
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    const line = `${req.method} ${req.originalUrl} ${res.statusCode} ${duration}ms`;
    if (res.statusCode >= 500) httpLog.error(line, { reqId: req.id });
    else if (res.statusCode >= 400) httpLog.warn(line, { reqId: req.id });
    else httpLog.info(line, { reqId: req.id });
  });
  next();
});

// Static assets (display page CSS, favicon)
app.use('/assets', express.static(path.join(__dirname, '..', 'public')));

// React app static assets (Vite output)
app.use('/app', express.static(path.join(__dirname, '..', 'frontend', 'dist')));

// Auth: register / login / logout / me / api-tokens
app.use('/auth', createAuthRouter());

// Device API — authenticated; req.namespace is resolved from the user (auth.js)
app.use('/api', requireAuth, createAPIRouter(broadcast, broadcastGlobal));

// Admin
app.use('/admin', createAdminRouter());

// Health check
app.get('/health', (req, res) => res.json({ status: 'ok', version: VERSION }));

// React app (SPA) — serve index for any other GET; the app handles auth state client-side
const reactIndex = path.join(__dirname, '..', 'frontend', 'dist', 'index.html');
app.use((req, res, next) => {
  if (req.method !== 'GET') return next();
  if (req.path.startsWith('/api') || req.path.startsWith('/auth')) {
    return res.status(404).json({ error: 'Not found' });
  }
  res.sendFile(reactIndex);
});

// Start
async function start() {
  await initDB();
  server.listen(PORT, () => {
    console.log(`\n  ╔══════════════════════════════════════╗`);
    console.log(`  ║         BOTBEAM v${VERSION.padEnd(21)}║`);
    console.log(`  ║   AI-Powered Virtual Display Platform ║`);
    console.log(`  ╚══════════════════════════════════════╝`);
    console.log(`\n  Landing:  http://localhost:${PORT}`);
    console.log(`  Health:   http://localhost:${PORT}/health\n`);
  });
}

start().catch(console.error);
