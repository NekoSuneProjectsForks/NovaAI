'use strict';
// Bot lifecycle: create/connect, auto-reconnect with backoff, auto-eat, and
// wiring the spawn hook to start the live view.
const mineflayer = require('mineflayer');
const { pathfinder, Movements } = require('mineflayer-pathfinder');
const { CFG } = require('./config');
const { state, log } = require('./state');
const { isFood } = require('./helpers');
const { startPublicSite } = require('./site');

function startAutoEat() {
  if (state.autoEatTimer) return;
  // Survival: automatically eat when hunger drops, so the bot heals (natural
  // regen needs a near-full hunger bar) and doesn't starve — like a real player.
  state.autoEatTimer = setInterval(async () => {
    const bot = state.bot;
    if (!bot || !state.connected || state.autoEating) return;
    if (typeof bot.food !== 'number' || bot.food > CFG.autoEatThreshold) return;
    const food = bot.inventory.items().find((i) => isFood(i.name));
    if (!food) return;
    state.autoEating = true;
    try {
      await bot.equip(food, 'hand');
      await bot.consume();
    } catch (e) { /* full / interrupted */ } finally {
      state.autoEating = false;
    }
  }, 4000);
}

function scheduleReconnect(reason) {
  if (state.reconnectTimer) return; // already scheduled
  const secs = Math.round(state.reconnectDelay / 1000);
  log(`disconnected (${reason}); reconnecting in ${secs}s`);
  state.reconnectTimer = setTimeout(() => {
    state.reconnectTimer = null;
    try {
      createBot();
    } catch (e) {
      log('reconnect failed: ' + ((e && e.message) || e));
      scheduleReconnect('retry');
    }
  }, state.reconnectDelay);
  state.reconnectDelay = Math.min(60000, Math.floor(state.reconnectDelay * 1.5));
}

function createBot() {
  const opts = {
    host: CFG.host,
    port: CFG.port,
    username: CFG.username,
    auth: CFG.auth === 'microsoft' ? 'microsoft' : 'offline',
  };
  if (CFG.auth === 'microsoft') {
    opts.profilesFolder = CFG.profilesFolder;
    opts.onMsaCode = (data) => {
      log('MICROSOFT LOGIN REQUIRED: go to ' + (data.verification_uri || 'https://microsoft.com/link')
        + ' and enter code ' + (data.user_code || '(see console)'));
      if (data.message) log(data.message);
    };
  }
  if (CFG.version) opts.version = String(CFG.version);

  if (state.bot) {
    try { state.bot.removeAllListeners(); } catch (e) { /* ignore */ }
  }

  const bot = mineflayer.createBot(opts);
  state.bot = bot;
  bot.loadPlugin(pathfinder);
  try {
    bot.loadPlugin(require('mineflayer-tool').plugin); // auto best-tool for mining
  } catch (e) { /* optional dep */ }

  bot.once('spawn', () => {
    state.connected = true;
    state.reconnectDelay = 5000;
    try { bot.pathfinder.setMovements(new Movements(bot)); } catch (e) { /* ignore */ }
    startPublicSite();
    startAutoEat();
    log(`spawned as ${bot.username}${CFG.owner ? `, owner = ${CFG.owner}` : ''}`);
  });

  // Auto-reconnect on disconnect/kick so a server restart or blip recovers.
  bot.on('end', (reason) => { state.connected = false; scheduleReconnect(reason || 'end'); });
  bot.on('kicked', (reason) => {
    state.lastError = 'kicked: ' + reason;
    state.connected = false;
    log('kicked: ' + reason);
    scheduleReconnect('kicked');
  });
  bot.on('error', (err) => {
    state.lastError = String((err && err.message) || err);
    log('error: ' + state.lastError);
    if (!state.connected) scheduleReconnect('error');
  });
  bot.on('chat', (username, message) => {
    if (!username || username === bot.username) return;
    state.chatLog.push({ username, message: String(message).slice(0, 140) });
    if (state.chatLog.length > 20) state.chatLog.shift();
  });
}

module.exports = { createBot, scheduleReconnect };
