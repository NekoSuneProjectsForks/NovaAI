'use strict';
// Single public site on VIEWER_PORT: dashboard + proxied 3D viewer (/world) +
// proxied inventory viewer, so the whole live view is one URL.
const http = require('http');
const { CFG } = require('./config');
const { state, log } = require('./state');
const { feedData } = require('./helpers');
const { viewDashboardHtml } = require('./dashboard');

function sendJson(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

function startPublicSite() {
  if (!CFG.viewerPort || state.publicStarted) return;
  const bot = state.bot;
  const viewerInternal = CFG.viewerPort + 1;
  const invInternal = CFG.viewerPort + 2;

  // 3D viewer internally under the /world prefix, with version fallback so a
  // very new server still renders with the highest supported textures.
  let viewerOk = false;
  try {
    const { mineflayer: mineflayerViewer, supportedVersions } = require('prismarine-viewer');
    let assetVersion = bot.version;
    if (CFG.viewerVersion) assetVersion = CFG.viewerVersion;
    else if ((supportedVersions || []).length && !supportedVersions.includes(bot.version)) {
      assetVersion = supportedVersions[supportedVersions.length - 1];
    }
    const viewerBot = assetVersion === bot.version
      ? bot
      : new Proxy(bot, { get(t, p) { return p === 'version' ? assetVersion : t[p]; } });
    mineflayerViewer(viewerBot, {
      port: viewerInternal, firstPerson: CFG.viewerFirstPerson, viewDistance: 6, prefix: '/world',
    });
    viewerOk = true;
    log(`3D view assets ${assetVersion}${assetVersion !== bot.version ? ` (server ${bot.version})` : ''}`);
  } catch (e) {
    log('3D view unavailable (' + ((e && e.message) || e) + ') — run npm install.');
  }

  let invOk = false;
  try {
    require('mineflayer-web-inventory')(bot, { port: invInternal });
    invOk = true;
  } catch (e) {
    log('Inventory view unavailable (' + ((e && e.message) || e) + ').');
  }

  let proxy = null;
  try {
    proxy = require('http-proxy').createProxyServer({ ws: true });
    proxy.on('error', () => { /* ignore transient proxy errors */ });
  } catch (e) {
    log('http-proxy missing — run npm install in node/minecraft-bridge.');
  }
  const viewerTarget = `http://127.0.0.1:${viewerInternal}`;
  const invTarget = `http://127.0.0.1:${invInternal}`;
  const worldHtml = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>world</title>'
    + '<style>*{margin:0;padding:0}</style></head><body>'
    + "<script>window.prefix='/world'</script>"
    + '<script type="text/javascript" src="/world/index.js"></script></body></html>';

  const site = http.createServer((req, res) => {
    const p = (req.url || '').split('?')[0];
    if (p === '/' || p === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(viewDashboardHtml());
    }
    if (p === '/feed') return sendJson(res, 200, feedData());
    if (p === '/world' || p === '/world/' || p === '/world/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(worldHtml);
    }
    if (proxy && p.startsWith('/world')) return proxy.web(req, res, { target: viewerTarget });
    if (proxy && p.startsWith('/inv')) {
      req.url = req.url.replace(/^\/inv/, '') || '/';
      return proxy.web(req, res, { target: invTarget });
    }
    if (proxy) return proxy.web(req, res, { target: invTarget });
    sendJson(res, 503, { ok: false, message: 'viewer proxy unavailable' });
  });
  site.on('upgrade', (req, socket, head) => {
    if (!proxy) return socket.destroy();
    const p = (req.url || '').split('?')[0];
    if (p.startsWith('/world')) proxy.ws(req, socket, head, { target: viewerTarget });
    else proxy.ws(req, socket, head, { target: invTarget });
  });
  site.on('error', (e) => log('live site error: ' + ((e && e.message) || e)));
  site.listen(CFG.viewerPort, '127.0.0.1', () => {
    state.publicStarted = true;
    log(`live view (one port): http://127.0.0.1:${CFG.viewerPort}  [3D ${viewerOk ? 'on' : 'off'}, inventory ${invOk ? 'on' : 'off'}]`);
  });
}

module.exports = { startPublicSite };
