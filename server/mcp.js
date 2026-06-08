const crypto = require('crypto');
const express = require('express');
const { McpServer } = require('@modelcontextprotocol/sdk/server/mcp.js');
const { StreamableHTTPServerTransport } = require('@modelcontextprotocol/sdk/server/streamableHttp.js');
const { registerTools } = require('../mcp/tools');
const store = require('./store');
const { logAPI, getIP } = require('./log');
const { createLogger } = require('./logger');

const log = createLogger('mcp');
const sessions = new Map();
const SESSION_TTL = 30 * 60 * 1000; // 30 minutes

// Evict stale sessions once a day
setInterval(() => {
  const now = Date.now();
  let evicted = 0;
  for (const [id, session] of sessions) {
    if (now - session.lastActivity > SESSION_TTL) {
      log.info('Session evicted', { sessionId: id, namespace: session.namespace });
      session.transport.close?.();
      session.server.close?.();
      sessions.delete(id);
      evicted++;
    }
  }
  if (evicted > 0) log.info('Eviction sweep', { evicted, remaining: sessions.size });
}, 24 * 60 * 60 * 1000);

function createDirectClient(broadcast, broadcastGlobal, ip) {
  return {
    listDevices: async (ns) => {
      try {
        logAPI(ns, 'list_devices', { ip });
        return await store.loadDevices(ns);
      } catch (err) {
        log.error('listDevices failed', { namespace: ns, error: err.message });
        throw err;
      }
    },
    createDevice: async (ns, name, content, pickupMode) => {
      try {
        logAPI(ns, 'create_device', { device: name, contentType: content?.type, pickupMode, ip });
        const device = await store.createDevice(ns, name, content || null, pickupMode);
        broadcastGlobal(ns, { event: 'device_created', device });
        return device;
      } catch (err) {
        log.error('createDevice failed', { namespace: ns, device: name, error: err.message });
        throw err;
      }
    },
    updateDevice: async (ns, id, updates) => {
      try {
        logAPI(ns, 'update_device', { device: id, contentType: updates.content?.type, ip });
        const device = await store.updateDevice(ns, id, updates);
        if (!device) throw new Error('Device not found');
        broadcastGlobal(ns, { event: 'device_updated', device });
        return device;
      } catch (err) {
        log.error('updateDevice failed', { namespace: ns, device: id, error: err.message });
        throw err;
      }
    },
    deleteDevice: async (ns, id) => {
      try {
        logAPI(ns, 'delete_device', { device: id, ip });
        const ok = await store.deleteDevice(ns, id);
        if (ok) {
          broadcastGlobal(ns, { event: 'device_deleted', deviceId: id });
        }
        return { ok };
      } catch (err) {
        log.error('deleteDevice failed', { namespace: ns, device: id, error: err.message });
        throw err;
      }
    },
    resetDevices: async (ns) => {
      try {
        logAPI(ns, 'reset_devices', { ip });
        await store.resetDevices(ns);
        broadcastGlobal(ns, { event: 'devices_reset' });
      } catch (err) {
        log.error('resetDevices failed', { namespace: ns, error: err.message });
        throw err;
      }
    },
    listDropboxes: async (ns) => {
      try {
        logAPI(ns, 'list_dropboxes', { ip });
        return await store.loadDropboxes(ns);
      } catch (err) {
        log.error('listDropboxes failed', { namespace: ns, error: err.message });
        throw err;
      }
    },
    pickupDropbox: async (ns, deviceId, pickedUpBy) => {
      try {
        logAPI(ns, 'pickup_dropbox', { device: deviceId, ip });
        const device = await store.pickupDropbox(ns, deviceId, pickedUpBy);
        if (!device) throw new Error('Device not found');
        broadcastGlobal(ns, { event: 'device_picked_up', deviceId, pickedUpBy });
        return device;
      } catch (err) {
        log.error('pickupDropbox failed', { namespace: ns, device: deviceId, error: err.message });
        throw err;
      }
    },
  };
}

function createRouter(broadcast, broadcastGlobal) {
  const router = express.Router({ mergeParams: true });

  router.all('/', async (req, res) => {
    try {
      const namespace = req.namespace;

      // CORS
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept, Mcp-Session-Id');
      res.setHeader('Access-Control-Expose-Headers', 'Mcp-Session-Id');

      if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

      const sessionId = req.headers['mcp-session-id'];

      if (req.method === 'POST') {
        const body = req.body;

        const isInit = Array.isArray(body)
          ? body.some(m => m.method === 'initialize')
          : body.method === 'initialize';

        if (sessionId && sessions.has(sessionId)) {
          const session = sessions.get(sessionId);
          session.lastActivity = Date.now();
          log.debug('Session active', { sessionId, namespace });
          await session.transport.handleRequest(req, res, body);
        } else if (isInit) {
          const ip = getIP(req);
          const client = createDirectClient(broadcast, broadcastGlobal, ip);

          const transport = new StreamableHTTPServerTransport({
            sessionIdGenerator: () => crypto.randomUUID(),
            onsessioninitialized: (id) => {
              sessions.set(id, { transport, server: mcpServer, namespace, lastActivity: Date.now() });
              log.info('Session created', { sessionId: id, namespace, ip });
            },
          });

          const { MCP_VERSION } = require('../mcp/tools');
          const mcpServer = new McpServer({ name: 'botbeam', version: MCP_VERSION });
          registerTools(mcpServer, namespace, client);
          await mcpServer.connect(transport);
          await transport.handleRequest(req, res, body);
        } else {
          log.warn('Session expired', { sessionId, namespace });
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ jsonrpc: '2.0', error: { code: -32600, message: 'Session expired, please re-initialize' }, id: null }));
        }
      } else if (req.method === 'GET') {
        if (sessionId && sessions.has(sessionId)) {
          const session = sessions.get(sessionId);
          session.lastActivity = Date.now();
          await session.transport.handleRequest(req, res);
        } else {
          log.warn('Session not found (GET)', { sessionId, namespace });
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ jsonrpc: '2.0', error: { code: -32600, message: 'Session not found' }, id: null }));
        }
      } else if (req.method === 'DELETE') {
        if (sessionId && sessions.has(sessionId)) {
          const session = sessions.get(sessionId);
          await session.transport.handleRequest(req, res);
          sessions.delete(sessionId);
          log.info('Session deleted', { sessionId, namespace });
        } else {
          res.writeHead(204); res.end();
        }
      }
    } catch (err) {
      log.error('MCP request failed', { reqId: req.id, error: err.message, stack: err.stack });
      if (!res.headersSent) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ jsonrpc: '2.0', error: { code: -32603, message: 'Internal error' }, id: null }));
      }
    }
  });

  return router;
}

module.exports = { createRouter };
