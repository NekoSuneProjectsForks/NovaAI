/*
 * NovaAI Minecraft bridge — entry point.
 *
 * A Mineflayer bot exposed over a local HTTP API. NovaAI's Python game agent
 * (the LLM "brain") drives it; this process only translates high-level verbs
 * into Mineflayer calls and serves the live-view dashboard.
 *
 * The implementation is split into lib/ modules so things are easy to find:
 *   lib/config.js     CLI/env parsing + static gameplay data tables
 *   lib/state.js      shared mutable runtime state + log + sleep
 *   lib/helpers.js    world sensing, inventory helpers, observe()/feedData()
 *   lib/actions.js    every high-level verb (act) + multi-step action helpers
 *   lib/bot.js        bot lifecycle: connect, auto-reconnect, auto-eat
 *   lib/site.js       single-port live view (dashboard + 3D + inventory proxy)
 *   lib/dashboard.js  the Tailwind dashboard HTML
 *   lib/server.js     the local control API (health/observe/feed/thought/act)
 *
 * Config comes from CLI args, falling back to environment variables, so it can
 * run either way (offline/LAN or an online Microsoft account).
 */
'use strict';

const { createBot } = require('./lib/bot');
const { startApiServer } = require('./lib/server');
const { state, log } = require('./lib/state');

// Crash guards: a stray error from mineflayer/pathfinder/a plugin must not kill
// the whole bridge. Log it and keep running; if the bot died, schedule a
// reconnect so it recovers on its own.
function softRecover(kind, err) {
  log(`${kind}: ${(err && err.stack) || (err && err.message) || err}`);
  try {
    if (!state.connected && !state.reconnectTimer) {
      // Lazy require to avoid a cycle at load time.
      require('./lib/bot').scheduleReconnect(kind);
    }
  } catch (e) { /* ignore */ }
}

process.on('uncaughtException', (err) => softRecover('uncaughtException', err));
process.on('unhandledRejection', (err) => softRecover('unhandledRejection', err));

createBot();
startApiServer();
