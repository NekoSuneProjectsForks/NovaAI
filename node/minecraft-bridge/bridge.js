/*
 * NovaAI Minecraft bridge.
 *
 * A thin Mineflayer bot exposed over a local HTTP API. NovaAI's Python game
 * agent (the LLM "brain") calls:
 *   GET  /health   -> { ok, connected }
 *   GET  /observe  -> structured world state
 *   POST /act      -> { verb, args } executes a high-level action
 *
 * The brain stays in Python; this process only translates high-level verbs
 * into Mineflayer calls.
 */
'use strict';

const http = require('http');
const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');

// ── arg parsing ────────────────────────────────────────────────────────────
function getArg(name, fallback) {
  const idx = process.argv.indexOf('--' + name);
  return idx !== -1 && idx + 1 < process.argv.length ? process.argv[idx + 1] : fallback;
}

const HOST = getArg('host', '127.0.0.1');
const PORT = parseInt(getArg('port', '25565'), 10);
const USERNAME = getArg('username', 'NovaAI');
const BRIDGE_PORT = parseInt(getArg('bridge-port', '8767'), 10);
const AUTH = getArg('auth', 'offline'); // 'offline' | 'microsoft'

let bot = null;
let connected = false;
let lastError = '';

function createBot() {
  bot = mineflayer.createBot({
    host: HOST,
    port: PORT,
    username: USERNAME,
    auth: AUTH === 'microsoft' ? 'microsoft' : 'offline',
  });

  bot.loadPlugin(pathfinder);

  bot.once('spawn', () => {
    connected = true;
    try {
      const defaultMove = new Movements(bot);
      bot.pathfinder.setMovements(defaultMove);
    } catch (e) { /* ignore */ }
  });

  bot.on('end', () => { connected = false; });
  bot.on('error', (err) => { lastError = String(err && err.message || err); });
  bot.on('kicked', (reason) => { lastError = 'kicked: ' + reason; connected = false; });
}

// ── observation ──────────────────────────────────────────────────────────────
function observe() {
  if (!bot || !connected || !bot.entity) {
    return { connected: false };
  }
  const pos = bot.entity.position;
  const inventory = bot.inventory.items().map((i) => ({ name: i.name, count: i.count }));

  const nearbyBlocks = [];
  try {
    const seen = new Set();
    const base = bot.entity.position.floored();
    const offsets = [[1,0,0],[-1,0,0],[0,0,1],[0,0,-1],[0,1,0],[0,-1,0],[2,0,0],[-2,0,0],[0,0,2],[0,0,-2]];
    for (const [dx,dy,dz] of offsets) {
      const block = bot.blockAt(base.offset(dx, dy, dz));
      if (block && block.name && block.name !== 'air' && !seen.has(block.name)) {
        seen.add(block.name);
        nearbyBlocks.push(block.name);
      }
    }
  } catch (e) { /* ignore */ }

  const nearbyEntities = [];
  try {
    for (const id in bot.entities) {
      const e = bot.entities[id];
      if (e === bot.entity || !e.position) continue;
      if (e.position.distanceTo(bot.entity.position) < 16) {
        nearbyEntities.push(e.name || e.username || (e.kind || 'entity'));
      }
      if (nearbyEntities.length >= 10) break;
    }
  } catch (e) { /* ignore */ }

  return {
    connected: true,
    health: bot.health,
    food: bot.food,
    timeOfDay: bot.time ? bot.time.timeOfDay : undefined,
    position: { x: Math.round(pos.x), y: Math.round(pos.y), z: Math.round(pos.z) },
    inventory,
    nearbyBlocks,
    nearbyEntities,
  };
}

// ── actions ────────────────────────────────────────────────────────────────
async function act(verb, args) {
  if (!bot || !connected) return { ok: false, message: 'not connected' };
  args = args || {};
  try {
    switch (verb) {
      case 'say':
        bot.chat(String(args.text || '').slice(0, 200));
        return { ok: true, message: 'said it' };

      case 'goto': {
        if (args.x !== undefined && args.z !== undefined) {
          const y = args.y !== undefined ? args.y : bot.entity.position.y;
          await bot.pathfinder.goto(new goals.GoalNear(args.x, y, args.z, 1));
          return { ok: true, message: `arrived near ${args.x},${y},${args.z}` };
        }
        return { ok: false, message: 'goto needs x and z' };
      }

      case 'mine':
      case 'collect': {
        const name = String(args.name || args.block || '').toLowerCase();
        if (!name) return { ok: false, message: 'need a block name' };
        const ids = [];
        for (const key in bot.registry.blocksByName) {
          if (key.includes(name)) ids.push(bot.registry.blocksByName[key].id);
        }
        if (!ids.length) return { ok: false, message: `unknown block ${name}` };
        const block = bot.findBlock({ matching: ids, maxDistance: 48 });
        if (!block) return { ok: false, message: `no ${name} nearby` };
        await bot.pathfinder.goto(new goals.GoalNear(block.position.x, block.position.y, block.position.z, 1));
        await bot.dig(bot.blockAt(block.position) || block);
        return { ok: true, message: `mined ${name}` };
      }

      case 'craft': {
        const name = String(args.name || args.item || '').toLowerCase();
        const item = bot.registry.itemsByName[name];
        if (!item) return { ok: false, message: `unknown item ${name}` };
        const table = bot.findBlock({ matching: bot.registry.blocksByName.crafting_table ? [bot.registry.blocksByName.crafting_table.id] : [], maxDistance: 8 });
        const recipes = bot.recipesFor(item.id, null, 1, table || null);
        if (!recipes.length) return { ok: false, message: `no recipe for ${name} (need ingredients/table?)` };
        await bot.craft(recipes[0], args.count || 1, table || null);
        return { ok: true, message: `crafted ${name}` };
      }

      case 'place': {
        const name = String(args.name || args.block || '').toLowerCase();
        const item = bot.inventory.items().find((i) => i.name.includes(name));
        if (!item) return { ok: false, message: `no ${name} in inventory` };
        const ref = bot.blockAt(bot.entity.position.offset(0, -1, 0));
        if (!ref) return { ok: false, message: 'no reference block to place on' };
        await bot.equip(item, 'hand');
        await bot.placeBlock(ref, { x: 0, y: 1, z: 0 });
        return { ok: true, message: `placed ${name}` };
      }

      case 'look': {
        const yaw = args.yaw !== undefined ? args.yaw : bot.entity.yaw;
        const pitch = args.pitch !== undefined ? args.pitch : 0;
        await bot.look(yaw, pitch, false);
        return { ok: true, message: 'looked around' };
      }

      case 'stop':
        try { bot.pathfinder.setGoal(null); } catch (e) {}
        bot.clearControlStates();
        return { ok: true, message: 'stopped' };

      case 'wait':
        return { ok: true, message: 'waited' };

      default:
        return { ok: false, message: `unknown verb ${verb}` };
    }
  } catch (e) {
    return { ok: false, message: String(e && e.message || e) };
  }
}

// ── HTTP server ──────────────────────────────────────────────────────────────
function sendJson(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(body);
}

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    return sendJson(res, 200, { ok: true, connected, lastError });
  }
  if (req.method === 'GET' && req.url === '/observe') {
    return sendJson(res, 200, observe());
  }
  if (req.method === 'POST' && req.url === '/act') {
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

createBot();
server.listen(BRIDGE_PORT, '127.0.0.1', () => {
  // eslint-disable-next-line no-console
  console.log(`[novaai-bridge] listening on 127.0.0.1:${BRIDGE_PORT}, connecting to ${HOST}:${PORT}`);
});
