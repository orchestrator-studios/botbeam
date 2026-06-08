const store = require('./store');

async function namespaceMiddleware(req, res, next) {
  const ns = req.params.namespace;
  const row = await store.getNamespace(ns);
  if (!row) return res.status(404).json({ error: 'Namespace not found' });
  req.namespace = ns;
  store.touchNamespace(ns).catch(() => {});
  next();
}

module.exports = { namespaceMiddleware };
