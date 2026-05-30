'use strict';
// The local control API the Python agent talks to:
//   GET  /health   -> { ok, connected }
//   GET  /observe  -> structured world state
//   GET  /feed     -> dashboard data (stats + chat + thoughts)
//   POST /thought  -> push a narrated thought for the dashboard
//   POST /act      -> { verb, args } run a high-level action
//   GET  /view, /  -> the live dashboard (also served on the viewer port)
const http = require('http');
const { CFG } = require('./config');
const { state, log } = require('./state');
const { observe, feedData } = require('./helpers');
const { act } = require('./actions');
const { viewDashboardHtml } = require('./dashboard');

function sendJson(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

function startApiServer() {
  const server = http.createServer((req, res) => {
    const p = (req.url || '').split('?')[0];

    if (req.method === 'GET' && (p === '/view' || p === '/')) {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(viewDashboardHtml());
    }
    if (req.method === 'GET' && p === '/health') {
      return sendJson(res, 200, { ok: true, connected: state.connected, lastError: state.lastError });
    }
    if (req.method === 'GET' && p === '/observe') {
      return sendJson(res, 200, observe());
    }
    if (req.method === 'GET' && p === '/feed') {
      return sendJson(res, 200, feedData());
    }
    if (req.method === 'POST' && p === '/thought') {
      let data = '';
      req.on('data', (c) => { data += c; });
      req.on('end', () => {
        try {
          const t = JSON.parse(data || '{}').text;
          if (t) { state.thoughts.push(String(t).slice(0, 300)); if (state.thoughts.length > 60) state.thoughts.shift(); }
        } catch (e) { /* ignore */ }
        sendJson(res, 200, { ok: true });
      });
      return;
    }
    if (req.method === 'POST' && p === '/act') {
      let data = '';
      req.on('data', (chunk) => { data += chunk; });
      req.on('end', async () => {
        let payload = {};
        try { payload = JSON.parse(data || '{}'); } catch (e) { /* ignore */ }
        const result = await act(payload.verb, payload.args);
        sendJson(res, 200, result);
      });
      return;
    }
    sendJson(res, 404, { ok: false, message: 'not found' });
  });

  server.on('error', (e) => {
    log('API server error: ' + ((e && e.message) || e)
      + (e && e.code === 'EADDRINUSE' ? ` (port ${CFG.bridgePort} already in use)` : ''));
  });
  server.listen(CFG.bridgePort, '127.0.0.1', () => {
    log(`listening on 127.0.0.1:${CFG.bridgePort}, connecting to ${CFG.host}:${CFG.port} (auth=${CFG.auth})`);
  });
  return server;
}

module.exports = { startApiServer };
