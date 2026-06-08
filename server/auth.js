const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const express = require('express');
const store = require('./store');
const users = require('./users');
const { createLogger } = require('./logger');

const log = createLogger('auth');

// Matches the kh / table-that house pattern: bcrypt password hashing + JWT (HS256)
// bearer tokens carrying sub/user_id/org_id/username/role. Stateless — the client
// stores the token (browser: localStorage; agent: a creds file) and sends it as
// `Authorization: Bearer <jwt>`. One credential type for both clients.
const JWT_SECRET = process.env.JWT_SECRET_KEY || 'dev-insecure-secret-change-me';
const ALGORITHM = 'HS256';
const BROWSER_TOKEN_TTL = '7d';
const AGENT_TOKEN_TTL = '365d';
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

if (!process.env.JWT_SECRET_KEY) {
  log.warn('JWT_SECRET_KEY not set — using an insecure dev default. Set it in .env for any real use.');
}

const hashPassword = (pw) => bcrypt.hashSync(pw, 10);
const verifyPassword = (pw, hash) => bcrypt.compareSync(pw, hash);

function createToken(user, expiresIn) {
  const payload = {
    sub: user.email,
    user_id: user.id,
    org_id: user.org_id,
    username: user.email.split('@')[0],
    role: user.role,
  };
  return jwt.sign(payload, JWT_SECRET, { algorithm: ALGORITHM, expiresIn });
}

function tokenResponse(user, expiresIn) {
  return {
    access_token: createToken(user, expiresIn),
    token_type: 'bearer',
    user_id: user.id,
    org_id: user.org_id,
    role: user.role,
    email: user.email,
    username: user.email.split('@')[0],
  };
}

async function userFromToken(token) {
  let payload;
  try {
    payload = jwt.verify(token, JWT_SECRET, { algorithms: [ALGORITHM] });
  } catch {
    return null;
  }
  const user = await users.getUserById(payload.user_id);
  if (!user || !user.is_active) return null;
  return user;
}

async function resolveUser(req) {
  const authz = req.headers['authorization'];
  if (!authz || !authz.startsWith('Bearer ')) return null;
  return userFromToken(authz.slice(7).trim());
}

async function requireAuth(req, res, next) {
  try {
    const user = await resolveUser(req);
    if (!user) return res.status(401).json({ error: 'Not authenticated' });
    req.user = user;
    req.namespace = user.namespace_id; // store.js is namespace-scoped
    next();
  } catch (err) {
    log.error('requireAuth failed', { error: err.message });
    res.status(500).json({ error: 'Auth error' });
  }
}

// For the WebSocket upgrade: the browser passes the JWT as ?token= (browsers can't
// set Authorization on a WS handshake).
async function namespaceFromToken(token) {
  if (!token) return null;
  const user = await userFromToken(token);
  return user ? user.namespace_id : null;
}

function createAuthRouter() {
  const router = express.Router();
  const h = (fn) => (req, res) => Promise.resolve(fn(req, res)).catch((err) => {
    log.error('auth route failed', { path: req.path, error: err.message });
    if (!res.headersSent) res.status(500).json({ error: 'Internal error' });
  });

  router.post('/register', h(async (req, res) => {
    const { email, password, full_name } = req.body || {};
    if (!email || !EMAIL_RE.test(email)) return res.status(400).json({ error: 'Valid email required' });
    if (!password || password.length < 8) return res.status(400).json({ error: 'Password must be at least 8 characters' });
    const normalized = String(email).toLowerCase();
    if (await users.getUserByEmail(normalized)) return res.status(409).json({ error: 'Email already registered' });

    const namespaceId = await store.createNamespace(null);
    const user = await users.createUser({
      email: normalized,
      passwordHash: hashPassword(password),
      namespaceId,
      fullName: full_name || null,
    });
    log.info('user registered', { email: normalized, org_id: user.org_id });
    res.status(201).json(tokenResponse(user, BROWSER_TOKEN_TTL));
  }));

  router.post('/login', h(async (req, res) => {
    const { email, password } = req.body || {};
    if (!email || !password) return res.status(400).json({ error: 'Email and password required' });
    const user = await users.getUserByEmail(String(email).toLowerCase());
    if (!user || !verifyPassword(password, user.password_hash)) {
      return res.status(401).json({ error: 'Invalid email or password' });
    }
    if (!user.is_active) return res.status(401).json({ error: 'Account is deactivated' });
    res.json(tokenResponse(user, BROWSER_TOKEN_TTL));
  }));

  router.get('/me', requireAuth, h(async (req, res) => {
    const u = req.user;
    res.json({ email: u.email, user_id: u.id, org_id: u.org_id, role: u.role, username: u.email.split('@')[0] });
  }));

  // Mint a long-lived token for the agent / orchestra skill (stored in a creds file).
  router.post('/agent-token', requireAuth, h(async (req, res) => {
    const name = (req.body && req.body.name) || 'orchestra';
    res.status(201).json({ access_token: createToken(req.user, AGENT_TOKEN_TTL), token_type: 'bearer', name });
  }));

  return router;
}

module.exports = { createAuthRouter, requireAuth, namespaceFromToken };
