const { WebSocketServer } = require('ws');
const { createLogger } = require('./logger');
const { namespaceFromToken } = require('./auth');

const log = createLogger('ws');

function createWSServer(httpServer) {
  const wss = new WebSocketServer({ server: httpServer });
  const clients = new Map(); // "namespace:deviceId" -> Set<ws>

  wss.on('connection', async (ws, req) => {
    const params = new URL(req.url, 'http://localhost').searchParams;
    const device = params.get('device') || '_global';

    // Namespace is resolved from the JWT (passed as ?token= on the WS handshake) — never the URL.
    let namespace;
    try {
      namespace = await namespaceFromToken(params.get('token'));
    } catch {
      namespace = null;
    }
    if (!namespace) {
      ws.close(1008, 'Not authenticated');
      return;
    }

    const key = `${namespace}:${device}`;
    if (!clients.has(key)) clients.set(key, new Set());
    clients.get(key).add(ws);
    log.info('Client connected', { key, clients: clients.get(key).size });

    ws.on('close', () => {
      const set = clients.get(key);
      if (set) {
        set.delete(ws);
        log.debug('Client disconnected', { key, remaining: set.size });
        if (set.size === 0) clients.delete(key);
      }
    });

    ws.on('error', (err) => {
      log.error('WebSocket error', { key, error: err.message });
    });
  });

  function broadcast(namespace, deviceId, message) {
    const key = `${namespace}:${deviceId}`;
    const set = clients.get(key);
    log.debug('Broadcast', { key, event: message.event, recipients: set ? set.size : 0 });
    if (!set) return;
    const data = JSON.stringify(message);
    for (const ws of set) {
      if (ws.readyState === 1) {
        try { ws.send(data); }
        catch (err) { log.error('Send failed', { key, error: err.message }); }
      }
    }
  }

  function broadcastGlobal(namespace, message) {
    broadcast(namespace, '_global', message);
  }

  return { broadcast, broadcastGlobal };
}

module.exports = { createWSServer };
