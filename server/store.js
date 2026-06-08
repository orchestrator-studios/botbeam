const { getPool } = require('./db');
const { nanoid } = require('nanoid');
const { createLogger } = require('./logger');

const log = createLogger('store');
const MAX_BODY_BYTES = 512 * 1024; // 500KB

const VALID_CONTENT_TYPES = new Set(['text', 'html', 'url', 'image', 'markdown', 'dashboard', 'list', 'table', 'json']);
const VALID_PICKUP_MODES = new Set(['single', 'multi']);

// Normalizes structured content types (table, dashboard, list) so the frontend
// always receives a consistent shape. Returns the body string to store.
function validateContent(type, body) {
  if (!type || typeof type !== 'string') throw new Error('Content type is required');
  if (!VALID_CONTENT_TYPES.has(type)) {
    throw new Error(`Invalid content type "${type}". Must be one of: ${[...VALID_CONTENT_TYPES].join(', ')}`);
  }
  if (body === undefined || body === null) throw new Error('Content body is required');

  let bodyStr = typeof body === 'string' ? body : JSON.stringify(body);

  // Normalize table: accept a flat array of objects and wrap in {columns, rows}
  if (type === 'table') {
    let parsed;
    try { parsed = JSON.parse(bodyStr); } catch { throw new Error('Table body must be valid JSON'); }

    if (Array.isArray(parsed)) {
      // Flat array of objects → infer columns from keys of first row
      if (parsed.length === 0) throw new Error('Table body array must not be empty');
      if (typeof parsed[0] !== 'object' || parsed[0] === null) throw new Error('Table rows must be objects');
      const keys = Object.keys(parsed[0]);
      const columns = keys.map(k => ({ id: k, label: k }));
      bodyStr = JSON.stringify({ columns, rows: parsed });
    } else if (parsed && typeof parsed === 'object') {
      if (!Array.isArray(parsed.columns) || !Array.isArray(parsed.rows)) {
        throw new Error('Table body must have "columns" and "rows" arrays');
      }
    } else {
      throw new Error('Table body must be a JSON array or {columns, rows} object');
    }
  }

  if (Buffer.byteLength(bodyStr, 'utf8') > MAX_BODY_BYTES) {
    throw new Error(`Content body too large (max ${MAX_BODY_BYTES / 1024}KB)`);
  }

  return bodyStr;
}

function rowToDevice(r) {
  const device = {
    id: r.id,
    name: r.name,
    createdAt: r.createdAt,
    content: r.content_type
      ? { type: r.content_type, body: r.content_body, updatedAt: r.content_updated_at }
      : null,
  };
  if (r.pickup_mode) {
    device.pickupMode = r.pickup_mode;
    device.pickupCount = r.pickup_count ?? 0;
  }
  return device;
}

const DEVICE_COLS = `id, name, created_at as createdAt, content_type, content_body, content_updated_at, pickup_mode, pickup_count`;

// ── Namespaces ──

async function createNamespace(ip) {
  const db = getPool();
  const id = nanoid(8);
  try {
    await db.query('INSERT INTO namespaces (id, ip_address) VALUES (?, ?)', [id, ip || null]);
    return id;
  } catch (err) {
    log.error('createNamespace failed', { ip, error: err.message });
    throw err;
  }
}

async function getNamespace(id) {
  const db = getPool();
  try {
    const [rows] = await db.query('SELECT * FROM namespaces WHERE id = ?', [id]);
    return rows[0] || null;
  } catch (err) {
    log.error('getNamespace failed', { id, error: err.message });
    throw err;
  }
}

async function touchNamespace(id) {
  const db = getPool();
  try {
    await db.query('UPDATE namespaces SET last_active = NOW() WHERE id = ?', [id]);
  } catch (err) {
    log.error('touchNamespace failed', { id, error: err.message });
    throw err;
  }
}

// ── Devices ──

async function loadDevices(namespace) {
  const db = getPool();
  try {
    const [rows] = await db.query(
      `SELECT ${DEVICE_COLS} FROM devices WHERE namespace = ? ORDER BY created_at`,
      [namespace]
    );
    return rows.map(rowToDevice);
  } catch (err) {
    log.error('loadDevices failed', { namespace, error: err.message });
    throw err;
  }
}

async function createDevice(namespace, name, content, pickupMode) {
  if (!name || typeof name !== 'string') throw new Error('Device name is required');
  if (name.length > 255) throw new Error('Device name too long (max 255 chars)');
  if (content) content.body = validateContent(content.type, content.body);
  if (pickupMode && !VALID_PICKUP_MODES.has(pickupMode)) {
    throw new Error(`Invalid pickup mode "${pickupMode}". Must be one of: ${[...VALID_PICKUP_MODES].join(', ')}`);
  }
  if (pickupMode && (!content || content.type !== 'json')) {
    throw new Error('Dropbox devices must use content type "json"');
  }

  const db = getPool();
  const id = nanoid(8);

  try {
    if (content) {
      await db.query(
        `INSERT INTO devices (id, namespace, name, content_type, content_body, content_updated_at, pickup_mode)
         VALUES (?, ?, ?, ?, ?, NOW(), ?)`,
        [id, namespace, name, content.type, content.body, pickupMode || null]
      );
    } else {
      await db.query(
        'INSERT INTO devices (id, namespace, name) VALUES (?, ?, ?)',
        [id, namespace, name]
      );
    }
    const [rows] = await db.query(
      `SELECT ${DEVICE_COLS} FROM devices WHERE namespace = ? AND id = ?`,
      [namespace, id]
    );
    return rowToDevice(rows[0]);
  } catch (err) {
    log.error('createDevice failed', { namespace, name, error: err.message });
    throw err;
  }
}

async function updateDevice(namespace, id, updates) {
  
  const db = getPool();
  const sets = [];
  const params = [];

  if (updates.name !== undefined) {
    if (!updates.name || typeof updates.name !== 'string') throw new Error('Device name is required');
    if (updates.name.length > 255) throw new Error('Device name too long (max 255 chars)');
    sets.push('name = ?');
    params.push(updates.name);
  }

  if ('content' in updates) {
    if (updates.content === null) {
      sets.push('content_type = NULL, content_body = NULL, content_updated_at = NULL');
    } else {
      updates.content.body = validateContent(updates.content.type, updates.content.body);
      sets.push('content_type = ?, content_body = ?, content_updated_at = NOW()');
      params.push(updates.content.type, updates.content.body);
    }
  }

  if (sets.length === 0) throw new Error('Nothing to update');

  params.push(namespace, id);

  try {
    const [result] = await db.query(
      `UPDATE devices SET ${sets.join(', ')} WHERE namespace = ? AND id = ?`,
      params
    );
    if (result.affectedRows === 0) return null;
    const [rows] = await db.query(
      `SELECT ${DEVICE_COLS} FROM devices WHERE namespace = ? AND id = ?`,
      [namespace, id]
    );
    return rowToDevice(rows[0]);
  } catch (err) {
    log.error('updateDevice failed', { namespace, id, error: err.message });
    throw err;
  }
}

async function deleteDevice(namespace, id) {
  const db = getPool();
  try {
    const [result] = await db.query(
      'DELETE FROM devices WHERE namespace = ? AND id = ?',
      [namespace, id]
    );
    return result.affectedRows > 0;
  } catch (err) {
    log.error('deleteDevice failed', { namespace, id, error: err.message });
    throw err;
  }
}

async function resetDevices(namespace) {
  const db = getPool();
  try {
    const [result] = await db.query(
      'DELETE FROM devices WHERE namespace = ?',
      [namespace]
    );
    return result.affectedRows;
  } catch (err) {
    log.error('resetDevices failed', { namespace, error: err.message });
    throw err;
  }
}

// ── Dropbox ──

async function loadDropboxes(namespace) {
  const db = getPool();
  try {
    const [rows] = await db.query(
      `SELECT ${DEVICE_COLS} FROM devices WHERE namespace = ? AND pickup_mode IS NOT NULL ORDER BY created_at`,
      [namespace]
    );
    const devices = rows.map(rowToDevice);

    // Attach pickup history to each dropbox
    for (const device of devices) {
      const [pickups] = await db.query(
        `SELECT picked_up_by as pickedUpBy, picked_up_at as pickedUpAt FROM pickups WHERE namespace = ? AND device_id = ? ORDER BY picked_up_at DESC`,
        [namespace, device.id]
      );
      device.pickups = pickups;
    }

    return devices;
  } catch (err) {
    log.error('loadDropboxes failed', { namespace, error: err.message });
    throw err;
  }
}

async function pickupDropbox(namespace, deviceId, pickedUpBy) {
  if (!pickedUpBy || typeof pickedUpBy !== 'string') throw new Error('picked_up_by is required');
  if (pickedUpBy.length > 255) throw new Error('picked_up_by too long (max 255 chars)');

  const db = getPool();
  try {
    // Load the device
    const [devRows] = await db.query(
      `SELECT ${DEVICE_COLS} FROM devices WHERE namespace = ? AND id = ?`,
      [namespace, deviceId]
    );
    if (devRows.length === 0) return null;
    const device = rowToDevice(devRows[0]);

    if (!device.pickupMode) throw new Error('This device is not a dropbox');

    // For single-use, check if already picked up (atomic via INSERT...SELECT)
    if (device.pickupMode === 'single') {
      const [existing] = await db.query(
        'SELECT id FROM pickups WHERE namespace = ? AND device_id = ?',
        [namespace, deviceId]
      );
      if (existing.length > 0) throw new Error('This dropbox has already been picked up');
    }

    // Record the pickup and increment counter atomically
    await db.query(
      'INSERT INTO pickups (namespace, device_id, picked_up_by) VALUES (?, ?, ?)',
      [namespace, deviceId, pickedUpBy]
    );
    await db.query(
      'UPDATE devices SET pickup_count = pickup_count + 1 WHERE namespace = ? AND id = ?',
      [namespace, deviceId]
    );

    // Re-read device with updated pickup_count
    const [updated] = await db.query(
      `SELECT ${DEVICE_COLS} FROM devices WHERE namespace = ? AND id = ?`,
      [namespace, deviceId]
    );
    return rowToDevice(updated[0]);
  } catch (err) {
    log.error('pickupDropbox failed', { namespace, deviceId, error: err.message });
    throw err;
  }
}

// ── Admin ──

async function getActiveNamespaces() {
  const db = getPool();
  try {
    const [rows] = await db.query(
      `SELECT namespace, COUNT(*) as count, MAX(created_at) as lastActivity
       FROM api_log GROUP BY namespace ORDER BY lastActivity DESC`
    );
    return rows;
  } catch (err) {
    log.error('getActiveNamespaces failed', { error: err.message });
    throw err;
  }
}

async function getLogsByNamespace(namespace, limit = 100) {
  const db = getPool();
  try {
    const [rows] = await db.query(
      `SELECT action, device, content_type as contentType, ip_address as ip, created_at as createdAt
       FROM api_log WHERE namespace = ? ORDER BY created_at DESC LIMIT ?`,
      [namespace, limit]
    );
    return rows;
  } catch (err) {
    log.error('getLogsByNamespace failed', { namespace, error: err.message });
    throw err;
  }
}

module.exports = {
  createNamespace, getNamespace, touchNamespace,
  loadDevices, createDevice, updateDevice, deleteDevice, resetDevices,
  loadDropboxes, pickupDropbox,
  validateContent,
  getActiveNamespaces, getLogsByNamespace,
  MAX_BODY_BYTES, VALID_CONTENT_TYPES, VALID_PICKUP_MODES,
};
