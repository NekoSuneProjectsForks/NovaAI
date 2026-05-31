'use strict';
// All CLI-arg / env parsing and static data tables live here, so connection and
// gameplay constants are in one place instead of scattered through bridge.js.
const path = require('path');

function getArg(name, envName, fallback) {
  const idx = process.argv.indexOf('--' + name);
  if (idx !== -1 && idx + 1 < process.argv.length) return process.argv[idx + 1];
  if (envName && process.env[envName] !== undefined && process.env[envName] !== '') {
    return process.env[envName];
  }
  return fallback;
}

function parseHome(raw) {
  const s = String(raw || '');
  if (!s) return null;
  const p = s.split(',').map((n) => parseInt(n.trim(), 10));
  if (p.length === 3 && p.every((n) => !Number.isNaN(n))) return { x: p[0], y: p[1], z: p[2] };
  return null;
}

const CFG = {
  host: getArg('host', 'MC_HOST', '127.0.0.1'),
  port: parseInt(getArg('port', 'MC_PORT', '25565'), 10),
  username: getArg('username', 'MC_USERNAME', 'NovaAI'),
  bridgePort: parseInt(getArg('bridge-port', 'MC_BRIDGE_PORT', '8767'), 10),
  auth: getArg('auth', 'MC_AUTH', 'offline'), // 'offline' | 'microsoft'
  owner: String(getArg('owner', 'MC_OWNER_USERNAME', '')).toLowerCase(),
  profilesFolder: getArg('profiles-folder', 'MC_PROFILES_FOLDER', path.join(__dirname, '..', '.minecraft-auth')),
  version: getArg('version', 'MC_VERSION', false), // false = auto-detect
  viewerPort: parseInt(getArg('viewer-port', 'MC_VIEWER_PORT', '8768'), 10),
  viewerFirstPerson:
    String(getArg('viewer-first-person', 'MC_VIEWER_FIRST_PERSON', 'false')).toLowerCase() === 'true',
  viewerVersion: String(getArg('viewer-version', 'MC_VIEWER_VERSION', '')).trim(),
  home: parseHome(getArg('home', 'MC_HOME', '')),
  autoEatThreshold: 17, // eat to top up hunger so health regenerates
};

// ── static gameplay data ─────────────────────────────────────────────────────
const DATA = {
  HOSTILES: new Set([
    'zombie', 'husk', 'drowned', 'zombie_villager', 'skeleton', 'stray', 'wither_skeleton',
    'spider', 'cave_spider', 'creeper', 'witch', 'slime', 'magma_cube', 'blaze', 'ghast',
    'enderman', 'endermite', 'silverfish', 'phantom', 'pillager', 'vindicator', 'evoker',
    'ravager', 'vex', 'guardian', 'elder_guardian', 'shulker', 'hoglin', 'zoglin', 'piglin_brute',
    'warden', 'breeze', 'bogged',
  ]),
  FOODS: ['cooked', 'steak', 'bread', 'apple', 'carrot', 'baked_potato',
    'melon_slice', 'cookie', 'pumpkin_pie', 'beetroot_soup', 'mushroom_stew',
    'rabbit_stew', 'golden_apple', 'sweet_berries', 'glow_berries', 'honey_bottle',
    'dried_kelp', 'chicken', 'porkchop', 'beef', 'mutton', 'cod', 'salmon', 'potato'],
  RAW_FOODS: ['beef', 'porkchop', 'chicken', 'mutton', 'rabbit', 'cod', 'salmon', 'potato', 'kelp'],
  // Map everyday words to in-game names so "wood" finds logs, etc.
  NAME_ALIASES: { wood: 'log', wooden: 'log', timber: 'log', cobble: 'cobblestone' },
  ORE_KEYWORDS: ['coal_ore', 'copper_ore', 'iron_ore', 'gold_ore', 'redstone_ore',
    'lapis_ore', 'diamond_ore', 'emerald_ore', 'nether_gold_ore', 'nether_quartz_ore',
    'ancient_debris'],
  CROP_MATURE_AGE: { wheat: 7, carrots: 7, potatoes: 7, beetroots: 3, nether_wart: 3 },
  CROP_TO_SEED: {
    wheat: 'wheat_seeds', carrots: 'carrot', potatoes: 'potato',
    beetroots: 'beetroot_seeds', nether_wart: 'nether_wart',
  },
  ANIMAL_FOOD: {
    cow: 'wheat', sheep: 'wheat', mooshroom: 'wheat', goat: 'wheat',
    pig: 'carrot', chicken: 'wheat_seeds', rabbit: 'carrot',
    wolf: 'beef', cat: 'cod', ocelot: 'cod', horse: 'golden_carrot',
    donkey: 'golden_carrot', llama: 'hay_block', fox: 'sweet_berries',
    panda: 'bamboo', turtle: 'seagrass', bee: 'flower', frog: 'slime_ball',
  },
  FOOD_ANIMALS: ['cow', 'pig', 'chicken', 'sheep', 'rabbit', 'cod', 'salmon'],
  // Tool tiers best -> worst (lower index = better).
  TOOL_TIERS: ['netherite', 'diamond', 'iron', 'golden', 'stone', 'wooden'],
};

module.exports = { getArg, CFG, DATA };
