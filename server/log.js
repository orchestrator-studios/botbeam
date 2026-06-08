const { getPool } = require('./db');
const { createLogger } = require('./logger');

const log = createLogger('audit');

function normalizeIP(ip) {
  if (!ip) return null;
  if (ip === '::1' || ip === '::ffff:127.0.0.1') return '127.0.0.1';
  if (ip.startsWith('::ffff:')) return ip.slice(7);
  return ip;
}

function logAPI(namespace, action, { device, contentType, body, ip } = {}) {
  const bodyStr = body ? (typeof body === 'string' ? body : JSON.stringify(body)) : null;
  getPool().query(
    'INSERT INTO api_log (namespace, action, device, content_type, body, ip_address) VALUES (?, ?, ?, ?, ?, ?)',
    [namespace, action, device || null, contentType || null, bodyStr, normalizeIP(ip)]
  ).catch((err) => {
    log.warn('Failed to write audit log', { namespace, action, error: err.message });
  });
}

function getIP(req) {
  return req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket.remoteAddress;
}

module.exports = { normalizeIP, logAPI, getIP };
