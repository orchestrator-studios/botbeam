const crypto = require('crypto');

const LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
const currentLevel = LEVELS[process.env.LOG_LEVEL?.toLowerCase()] ?? LEVELS.info;

function format(level, component, msg, data) {
  const ts = new Date().toISOString();
  const prefix = `${ts} [${level.toUpperCase()}] [${component}]`;
  if (data && Object.keys(data).length > 0) {
    return `${prefix} ${msg} ${JSON.stringify(data)}`;
  }
  return `${prefix} ${msg}`;
}

function createLogger(component) {
  return {
    debug: (msg, data) => currentLevel <= LEVELS.debug && console.debug(format('debug', component, msg, data)),
    info:  (msg, data) => currentLevel <= LEVELS.info  && console.log(format('info', component, msg, data)),
    warn:  (msg, data) => currentLevel <= LEVELS.warn  && console.warn(format('warn', component, msg, data)),
    error: (msg, data) => currentLevel <= LEVELS.error && console.error(format('error', component, msg, data)),
  };
}

function generateRequestId() {
  return crypto.randomUUID().slice(0, 8);
}

module.exports = { createLogger, generateRequestId };
