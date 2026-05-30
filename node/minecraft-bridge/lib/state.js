'use strict';
// Shared mutable runtime state for the bridge. One object every module reads and
// writes, so there are no scattered top-level `let`s.
const { CFG } = require('./config');

const state = {
  bot: null,
  connected: false,
  lastError: '',
  reconnectTimer: null,
  reconnectDelay: 5000, // grows with backoff, resets on successful spawn
  autoEating: false,
  autoEatTimer: null,
  chatLog: [], // recent in-game chat so the agent can read/react
  thoughts: [], // NovaAI's recent narrated thoughts/decisions (for the dashboard)
  homePos: CFG.home, // remembered home location (set_home / MC_HOME=x,y,z)
  publicStarted: false,
};

function log(msg) {
  // Printed to stdout; the Python driver forwards these lines to the UI.
  // eslint-disable-next-line no-console
  console.log('[novaai-bridge] ' + msg);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

module.exports = { state, log, sleep };
