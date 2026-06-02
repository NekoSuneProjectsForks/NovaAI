'use strict';
// Single public site on VIEWER_PORT: dashboard + proxied 3D viewer (/world) +
// proxied inventory viewer, so the whole live view is one URL.
const http = require('http');
const os = require('os');
const { CFG } = require('./config');
const { state, log } = require('./state');
const { feedData } = require('./helpers');
const { viewDashboardHtml } = require('./dashboard');

// Best-effort LAN IPv4 so the logged URL is reachable when bound to 0.0.0.0.
function localIp() {
  const ifaces = os.networkInterfaces();
  for (const name of Object.keys(ifaces)) {
    for (const ni of ifaces[name] || []) {
      if (ni.family === 'IPv4' && !ni.internal) return ni.address;
    }
  }
  return '127.0.0.1';
}

function sendJson(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

// Choose a texture/asset version both viewers can actually load. Their bundled
// assets lag the newest MC, so on e.g. a 1.21.11 server we spoof the highest
// supported version (1.21.4) or rendering/inventory break.
function safeAssetVersion(botVersion) {
  if (CFG.viewerVersion) return CFG.viewerVersion;
  try {
    const supported = require('prismarine-viewer').supportedVersions || [];
    if (supported.length && !supported.includes(botVersion)) {
      return supported[supported.length - 1];
    }
  } catch (e) { /* fall through */ }
  return botVersion;
}

// A thin proxy that only overrides `.version`, so a plugin loads assets/data for
// a supported version while everything else still comes from the real bot.
function versionProxy(bot, version) {
  if (version === bot.version) return bot;
  return new Proxy(bot, { get(t, p) { return p === 'version' ? version : t[p]; } });
}

// mineflayer-web-inventory does `mcAssets.textureContent[item.name].texture`,
// which throws for any item missing from the (older) asset set — crashing on
// every inventory update on a too-new server. Pre-load the asset version and
// wrap textureContent so missing items return a blank texture instead.
function hardenInventoryAssets(version) {
  try {
    const mcAssets = require('minecraft-assets')(version); // cached by the plugin
    if (mcAssets && mcAssets.textureContent && !mcAssets.__hardened) {
      const real = mcAssets.textureContent;
      const blank = { texture: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC' };
      mcAssets.textureContent = new Proxy(real, {
        get(t, name) { return t[name] !== undefined ? t[name] : blank; },
      });
      mcAssets.__hardened = true;
    }
  } catch (e) { /* if assets can't load, the plugin will just no-op */ }
}

function startPublicSite() {
  if (!CFG.viewerPort || state.publicStarted) return;
  const bot = state.bot;
  const viewerInternal = CFG.viewerPort + 1;
  const invInternal = CFG.viewerPort + 2;
  const assetVersion = safeAssetVersion(bot.version);
  const renderBot = versionProxy(bot, assetVersion);

  // 3D viewer internally under the /world prefix.
  let viewerOk = false;
  try {
    const { mineflayer: mineflayerViewer } = require('prismarine-viewer');
    mineflayerViewer(renderBot, {
      port: viewerInternal, firstPerson: CFG.viewerFirstPerson, viewDistance: 6, prefix: '/world',
    });
    viewerOk = true;
    log(`3D view assets ${assetVersion}${assetVersion !== bot.version ? ` (server ${bot.version})` : ''}`);
  } catch (e) {
    log('3D view unavailable (' + ((e && e.message) || e) + ') — run npm install.');
  }

  // Inventory viewer — version-proxied + hardened assets so it doesn't crash on
  // items missing from the older texture set.
  let invOk = false;
  try {
    hardenInventoryAssets(assetVersion);
    require('mineflayer-web-inventory')(renderBot, { port: invInternal });
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
  site.listen(CFG.viewerPort, CFG.viewerHost, () => {
    state.publicStarted = true;
    const shownHost = (CFG.viewerHost === '0.0.0.0' || CFG.viewerHost === '::') ? localIp() : CFG.viewerHost;
    log(`live view (one port): http://${shownHost}:${CFG.viewerPort}  [3D ${viewerOk ? 'on' : 'off'}, inventory ${invOk ? 'on' : 'off'}]`);
  });
}

module.exports = { startPublicSite };
