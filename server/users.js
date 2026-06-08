const { getPool } = require('./db');
const { nanoid } = require('nanoid');

// Users + organizations. Matches the kh / table-that pattern: a user belongs to an
// org and carries a role. Each BotBeam user also owns one namespace (their display
// set); auth resolves a request → user → namespace, and the namespace-scoped
// store.js does the rest.

const DEFAULT_ORG_ID = 'org_default';

async function createUser({ email, passwordHash, namespaceId, orgId = DEFAULT_ORG_ID, role = 'member', fullName = null }) {
  const db = getPool();
  const id = nanoid(12);
  await db.query(
    `INSERT INTO users (id, email, password_hash, full_name, org_id, role, namespace_id)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [id, email, passwordHash, fullName, orgId, role, namespaceId]
  );
  return getUserById(id);
}

async function getUserByEmail(email) {
  const db = getPool();
  const [rows] = await db.query('SELECT * FROM users WHERE email = ?', [email]);
  return rows[0] || null;
}

async function getUserById(id) {
  const db = getPool();
  const [rows] = await db.query('SELECT * FROM users WHERE id = ?', [id]);
  return rows[0] || null;
}

module.exports = { DEFAULT_ORG_ID, createUser, getUserByEmail, getUserById };
