'use strict';
// World-sensing + inventory helpers, plus observe()/feedData(). All read the
// live bot from shared state so they keep working across reconnects.
const { CFG, DATA } = require('./config');
const { state } = require('./state');

const {
  HOSTILES, FOODS, NAME_ALIASES, ORE_KEYWORDS, CROP_MATURE_AGE, CROP_TO_SEED,
  ANIMAL_FOOD, FOOD_ANIMALS, TOOL_TIERS,
} = DATA;
const owner = CFG.owner;

// ── entity sensing ───────────────────────────────────────────────────────────
function playerEntity(name) {
  const bot = state.bot;
  const want = String(name || owner || '').toLowerCase();
  if (!want || !bot) return null;
  for (const uname in bot.players) {
    if (uname.toLowerCase() === want) {
      const p = bot.players[uname];
      if (p && p.entity) return p.entity;
    }
  }
  return null;
}

function isHostile(entity) {
  return entity && entity.name && HOSTILES.has(String(entity.name).toLowerCase());
}

function nearestVillager(maxDist) {
  const bot = state.bot;
  maxDist = maxDist || 16;
  let best = null;
  let bestD = maxDist;
  for (const id in bot.entities) {
    const e = bot.entities[id];
    if (!e || !e.position) continue;
    if (String(e.name || '').toLowerCase() === 'villager') {
      const d = e.position.distanceTo(bot.entity.position);
      if (d < bestD) { bestD = d; best = e; }
    }
  }
  return best;
}

function nearestHostile(maxDist) {
  const bot = state.bot;
  maxDist = maxDist || 12;
  let best = null;
  let bestD = maxDist;
  for (const id in bot.entities) {
    const e = bot.entities[id];
    if (!isHostile(e) || !e.position) continue;
    const d = e.position.distanceTo(bot.entity.position);
    if (d < bestD) { bestD = d; best = e; }
  }
  return best;
}

function entityByName(name) {
  const bot = state.bot;
  const want = String(name || '').toLowerCase();
  if (!want) return null;
  const p = playerEntity(want);
  if (p) return p;
  let best = null;
  let bestD = 64;
  for (const id in bot.entities) {
    const e = bot.entities[id];
    if (!e || e === bot.entity || !e.position) continue;
    const nm = String(e.username || e.name || '').toLowerCase();
    if (nm && (nm === want || nm.includes(want))) {
      const d = e.position.distanceTo(bot.entity.position);
      if (d < bestD) { bestD = d; best = e; }
    }
  }
  return best;
}

// ── item / block naming ──────────────────────────────────────────────────────
function armorSlotForItem(name) {
  name = String(name).toLowerCase();
  if (name.includes('helmet') || name.includes('cap') || name.includes('turtle')) return 'head';
  if (name.includes('chestplate') || name.includes('elytra')) return 'torso';
  if (name.includes('leggings')) return 'legs';
  if (name.includes('boots')) return 'feet';
  return null;
}

function armorTier(name) {
  name = String(name).toLowerCase();
  const order = ['leather', 'gold', 'golden', 'chainmail', 'iron', 'diamond', 'netherite'];
  for (let i = order.length - 1; i >= 0; i--) if (name.includes(order[i])) return i;
  return -1;
}

function isFood(name) {
  name = String(name).toLowerCase();
  return FOODS.some((f) => name.includes(f));
}

function aliasName(name) {
  const n = String(name || '').toLowerCase().trim();
  return NAME_ALIASES[n] || n;
}

function resolveItem(name) {
  const bot = state.bot;
  const want = aliasName(name);
  if (!want) return null;
  if (bot.registry.itemsByName[want]) return bot.registry.itemsByName[want];
  for (const key in bot.registry.itemsByName) {
    if (key.includes(want)) return bot.registry.itemsByName[key];
  }
  return null;
}

function toolTier(name) {
  name = String(name).toLowerCase();
  return TOOL_TIERS.find((t) => name.startsWith(t + '_')) || '';
}

function idsForNames(names) {
  const bot = state.bot;
  const ids = [];
  for (const n of names) {
    const b = bot.registry.blocksByName[n];
    if (b) ids.push(b.id);
  }
  return ids;
}

function chestBlockIds() {
  const bot = state.bot;
  const ids = [];
  for (const n of ['chest', 'trapped_chest', 'barrel', 'ender_chest']) {
    if (bot.registry.blocksByName[n]) ids.push(bot.registry.blocksByName[n].id);
  }
  return ids;
}

function findInventory(...needles) {
  const bot = state.bot;
  return bot.inventory.items().find((i) => needles.some((n) => i.name.includes(n)));
}

function countInInventory(name) {
  const bot = state.bot;
  return bot.inventory.items()
    .filter((i) => i.name.includes(String(name).toLowerCase()))
    .reduce((s, i) => s + i.count, 0);
}

// ── blocks ───────────────────────────────────────────────────────────────────
// "Legit" exposure check: a block is exposed if at least one of its 6 faces
// touches air/water (i.e. you could actually see it while caving — not X-ray).
function isExposed(block) {
  const bot = state.bot;
  if (!block || !block.position) return false;
  const offsets = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
  for (const [dx, dy, dz] of offsets) {
    const n = bot.blockAt(block.position.offset(dx, dy, dz));
    if (!n || n.name === 'air' || n.name === 'cave_air' || n.name === 'void_air'
        || n.name === 'water' || n.boundingBox === 'empty') {
      return true;
    }
  }
  return false;
}

function cropAge(block) {
  try {
    if (block && block.getProperties) {
      const a = block.getProperties().age;
      if (a !== undefined) return parseInt(a, 10);
    }
  } catch (e) { /* ignore */ }
  return (block && typeof block.metadata === 'number') ? block.metadata : NaN;
}

function isMatureCrop(block) {
  if (!block) return false;
  const max = CROP_MATURE_AGE[block.name];
  if (max === undefined) return false;
  const age = cropAge(block);
  return !isNaN(age) && age >= max;
}

// ── world snapshot ───────────────────────────────────────────────────────────
function observe() {
  const bot = state.bot;
  if (!bot || !state.connected || !bot.entity) return { connected: false };
  const pos = bot.entity.position;
  const inventory = bot.inventory.items().map((i) => ({ name: i.name, count: i.count }));

  const nearbyBlocks = [];
  try {
    const seen = new Set();
    const base = pos.floored();
    const offsets = [[1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1], [0, 1, 0], [0, -1, 0], [2, 0, 0], [-2, 0, 0], [0, 0, 2], [0, 0, -2]];
    for (const [dx, dy, dz] of offsets) {
      const block = bot.blockAt(base.offset(dx, dy, dz));
      if (block && block.name && block.name !== 'air' && !seen.has(block.name)) {
        seen.add(block.name); nearbyBlocks.push(block.name);
      }
    }
  } catch (e) { /* ignore */ }

  const players = [];
  const hostiles = [];
  try {
    for (const id in bot.entities) {
      const e = bot.entities[id];
      if (e === bot.entity || !e.position) continue;
      const d = e.position.distanceTo(pos);
      if (e.type === 'player' && d < 48) {
        players.push({ name: e.username || e.name, distance: Math.round(d) });
      } else if (isHostile(e) && d < 24) {
        hostiles.push({ name: e.name, distance: Math.round(d) });
      }
    }
  } catch (e) { /* ignore */ }
  hostiles.sort((a, b) => a.distance - b.distance);

  const ownerEnt = playerEntity(owner);
  return {
    connected: true,
    owner: owner || null,
    ownerVisible: !!ownerEnt,
    ownerDistance: ownerEnt ? Math.round(ownerEnt.position.distanceTo(pos)) : null,
    health: bot.health,
    food: bot.food,
    timeOfDay: bot.time ? bot.time.timeOfDay : undefined,
    position: { x: Math.round(pos.x), y: Math.round(pos.y), z: Math.round(pos.z) },
    inventory,
    nearbyBlocks,
    players,
    nearbyHostiles: hostiles,
    recentChat: state.chatLog.slice(-8),
    home: state.homePos,
    homeDistance: state.homePos
      ? Math.round(Math.hypot(pos.x - state.homePos.x, pos.z - state.homePos.z)) : null,
  };
}

function feedData() {
  const o = observe();
  return {
    connected: state.connected,
    username: CFG.username,
    health: o.health, food: o.food, position: o.position,
    chat: state.chatLog.slice(-40),
    thoughts: state.thoughts.slice(-40),
  };
}

module.exports = {
  playerEntity, isHostile, nearestVillager, nearestHostile, entityByName,
  armorSlotForItem, armorTier, isFood, aliasName, resolveItem, toolTier,
  idsForNames, chestBlockIds, findInventory, countInInventory,
  isExposed, cropAge, isMatureCrop, observe, feedData,
};
