const express = require('express');
const store = require('./store');
const { logAPI, getIP } = require('./log');
const { createLogger } = require('./logger');

const log = createLogger('api');

// Wrap async route handlers so thrown errors become 500 responses
const asyncHandler = (fn) => (req, res, next) =>
  Promise.resolve(fn(req, res, next)).catch(next);

function createRouter(broadcast, broadcastGlobal) {
  const router = express.Router({ mergeParams: true });

  // Log write API calls (skip GETs — those are just browser fetches)
  router.use((req, res, next) => {
    if (req.method !== 'GET') {
      const action = `${req.method} ${req.path}`;
      logAPI(req.namespace, action, {
        device: req.params.id,
        contentType: req.body?.type,
        body: req.body && Object.keys(req.body).length > 0 ? req.body : null,
        ip: getIP(req),
      });
    }
    next();
  });

  // List devices (with content)
  router.get('/devices', asyncHandler(async (req, res) => {
    res.json(await store.loadDevices(req.namespace));
  }));

  // Create device (optionally with content, optionally as dropbox)
  router.post('/devices', asyncHandler(async (req, res) => {
    const { name, content, pickup_mode } = req.body;
    if (!name) return res.status(400).json({ error: 'name is required' });

    const device = await store.createDevice(req.namespace, name, content || null, pickup_mode || undefined);
    broadcastGlobal(req.namespace, { event: 'device_created', device });
    res.status(201).json(device);
  }));

  // Update device (name and/or content; content: null clears it)
  router.patch('/devices/:id', asyncHandler(async (req, res) => {
    const { name, content } = req.body;
    if (name === undefined && !('content' in req.body)) {
      return res.status(400).json({ error: 'name or content is required' });
    }

    const updates = {};
    if (name !== undefined) updates.name = name;
    if ('content' in req.body) updates.content = content;

    const device = await store.updateDevice(req.namespace, req.params.id, updates);
    if (!device) return res.status(404).json({ error: 'Device not found' });

    broadcastGlobal(req.namespace, { event: 'device_updated', device });
    res.json(device);
  }));

  // Delete device
  router.delete('/devices/:id', asyncHandler(async (req, res) => {
    const ok = await store.deleteDevice(req.namespace, req.params.id);
    if (!ok) return res.status(404).json({ error: 'Device not found' });
    broadcastGlobal(req.namespace, { event: 'device_deleted', deviceId: req.params.id });
    res.status(204).end();
  }));

  // Reset — delete all devices
  router.delete('/devices', asyncHandler(async (req, res) => {
    await store.resetDevices(req.namespace);
    broadcastGlobal(req.namespace, { event: 'devices_reset' });
    res.status(204).end();
  }));

  // List dropboxes (devices with pickup_mode set)
  router.get('/dropboxes', asyncHandler(async (req, res) => {
    res.json(await store.loadDropboxes(req.namespace));
  }));

  // Pick up a dropbox
  router.post('/devices/:id/pickup', asyncHandler(async (req, res) => {
    const { picked_up_by } = req.body;
    if (!picked_up_by) return res.status(400).json({ error: 'picked_up_by is required' });

    const device = await store.pickupDropbox(req.namespace, req.params.id, picked_up_by);
    if (!device) return res.status(404).json({ error: 'Device not found' });

    broadcastGlobal(req.namespace, { event: 'device_picked_up', deviceId: req.params.id, pickedUpBy: picked_up_by });
    res.json(device);
  }));

  // Proxy external URLs (bypasses X-Frame-Options)
  router.get('/proxy', async (req, res) => {
    const url = req.query.url;
    if (!url) return res.status(400).json({ error: 'url parameter required' });

    // SSRF protection: block internal/private URLs
    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname;
      if (
        parsed.protocol !== 'http:' && parsed.protocol !== 'https:' ||
        hostname === 'localhost' ||
        hostname === '127.0.0.1' ||
        hostname === '0.0.0.0' ||
        hostname === '::1' ||
        hostname === '[::1]' ||
        hostname.endsWith('.local') ||
        hostname.endsWith('.internal') ||
        hostname.startsWith('10.') ||
        hostname.startsWith('192.168.') ||
        /^172\.(1[6-9]|2\d|3[01])\./.test(hostname) ||
        hostname === '169.254.169.254' ||
        hostname.startsWith('169.254.')
      ) {
        return res.status(403).json({ error: 'Blocked: cannot proxy internal or private URLs' });
      }
    } catch {
      return res.status(400).json({ error: 'Invalid URL' });
    }

    try {
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        redirect: 'follow',
      });

      const contentType = response.headers.get('content-type') || 'text/html';
      const html = await response.text();

      // Inject a <base> tag so relative URLs resolve against the original site's origin
      const origin = new URL(url).origin;
      const baseTag = `<base href="${origin}/">`;
      const patched = html.replace(/<head([^>]*)>/i, `<head$1>${baseTag}`);

      res.setHeader('Content-Type', contentType);
      res.send(patched);
    } catch (err) {
      log.error('Proxy fetch failed', { reqId: req.id, url, error: err.message });
      res.status(502).json({ error: `Failed to fetch: ${err.message}` });
    }
  });

  // Error handler for async route failures
  router.use((err, req, res, next) => {
    log.error(`${req.method} ${req.path} failed`, { reqId: req.id, error: err.message, stack: err.stack });
    res.status(500).json({ error: 'Internal server error' });
  });

  return router;
}

module.exports = { createRouter };
