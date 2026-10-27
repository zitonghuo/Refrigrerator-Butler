'use strict';
// Pure business helpers for reports, recipes and daily todos.
// They never touch the database: service.js loads the home document and persists it.

const DAY = 86400000;
const ZONE = 8 * 3600000; // Asia/Shanghai, fixed offset (no DST)
const MAX_STATS_DAYS = 60;
const BUCKETS = ['in', 'consume', 'discard', 'adjust'];
const WRITE_KINDS = { '入库': 'in', '消耗': 'consume', '丢弃': 'discard', '盘点': 'adjust' };
const LOCATIONS = ['冷藏', '冷冻', '常温'];

const round = value => Math.round(value * 1e6) / 1e6;
const dayKey = ms => new Date(ms + ZONE).toISOString().slice(0, 10);

function band(expiry, now) {
  if (!expiry) return 'unknown';
  const days = (Date.parse(expiry + 'T23:59:59+08:00') - now) / 86400000;
  return days < 0 ? 'expired' : days <= 1 ? 'urgent' : days <= 3 ? 'soon' : days <= 7 ? 'week' : 'fresh';
}

function emptyBucket() { return { count: 0, units: {} }; }
function emptyTotals() {
  return { in: emptyBucket(), consume: emptyBucket(), discard: emptyBucket(), adjust: emptyBucket(), nearExpiryConsumed: emptyBucket() };
}
function addUnits(target, units, factor = 1) {
  for (const [unit, value] of Object.entries(units || {})) target[unit] = round((target[unit] || 0) + value * factor);
}
function addBucket(target, source) {
  target.count += source.count;
  addUnits(target.units, source.units);
}
function bucketOf(entry, name) {
  if (!entry[name]) entry[name] = emptyBucket();
  return entry[name];
}

// Accumulates one operation into home.stats. Called from service.record() inside the transaction.
function recordStats(home, item, kind, amount, now) {
  const key = WRITE_KINDS[kind];
  if (!key) return; // edits such as '修改资料' do not change stock
  const quantity = Number(amount);
  if (!Number.isFinite(quantity)) return;
  if (!home.stats || typeof home.stats !== 'object') home.stats = { since: now, days: {} };
  if (!home.stats.days || typeof home.stats.days !== 'object') home.stats.days = {};
  const day = dayKey(now);
  if (!home.stats.days[day]) home.stats.days[day] = {};
  const entry = home.stats.days[day];
  const bucket = bucketOf(entry, key);
  bucket.count += 1;
  addUnits(bucket.units, { [item.unit]: quantity });
  // "临期消耗" means the batch was already in today/3-day window when consumed.
  if (kind === '消耗' && ['urgent', 'soon'].includes(band(item.expiry, now))) {
    const near = bucketOf(entry, 'nearExpiryConsumed');
    near.count += 1;
    addUnits(near.units, { [item.unit]: quantity });
  }
  // Bound the document: keep a rolling window of daily stats.
  const cutoff = dayKey(now - MAX_STATS_DAYS * DAY);
  for (const key of Object.keys(home.stats.days)) if (key < cutoff) delete home.stats.days[key];
}

function normalizeDays(value) {
  return Number.isInteger(value) && [7, 30].includes(value) ? value : 7;
}

// Weekly/monthly report. Uses pre-aggregated stats when available, otherwise the
// last 200 events (best effort, marked partial) so old homes still get a number.
function summarize(home, data, now) {
  const days = normalizeDays(data && data.days);
  const from = dayKey(now - (days - 1) * DAY);
  const start = Date.parse(from + "T00:00:00+08:00");
  const to = dayKey(now);
  const totals = emptyTotals();
  const byDay = [];
  const stats = home.stats && home.stats.days && typeof home.stats.days === 'object' ? home.stats.days : null;

  if (stats) {
    for (const date of Object.keys(stats).sort()) {
      if (date < from || date > to) continue;
      const entry = stats[date] || {};
      const row = { date };
      let used = false;
      for (const bucket of [...BUCKETS, 'nearExpiryConsumed']) {
        const value = entry[bucket];
        if (!value) continue;
        row[bucket] = { count: value.count, units: { ...value.units } };
        addBucket(totals[bucket], value);
        used = true;
      }
      if (used) byDay.push(row);
    }
    return {
      days, from, to,
      source: 'stats',
      partial: Boolean(home.stats.since && home.stats.since > start),
      totals, byDay,
      amount: null,
      amountReason: '未记录价格，无法计算金额',
      note: '数量按单位分别统计，不跨单位换算；临期消耗指消耗时批次处于今天到期或 3 天内。'
    };
  }

  // Fallback: derive from the retained events (max 200) for homes that predate stats.
  const byDate = new Map();
  for (const event of home.events || []) {
    if (!event || typeof event.createdAt !== 'number' || event.createdAt < start || event.createdAt > now) continue;
    const bucket = WRITE_KINDS[event.kind];
    if (!bucket) continue;
    const date = dayKey(event.createdAt);
    if (!byDate.has(date)) byDate.set(date, {});
    const entry = byDate.get(date);
    const target = bucketOf(entry, bucket);
    target.count += 1;
    addUnits(target.units, { [event.unit]: Number(event.quantity) || 0 });
  }
  for (const date of [...byDate.keys()].sort()) {
    const entry = byDate.get(date);
    const row = { date };
    for (const bucket of BUCKETS) if (entry[bucket]) { row[bucket] = { count: entry[bucket].count, units: { ...entry[bucket].units } }; addBucket(totals[bucket], entry[bucket]); }
    byDay.push(row);
  }
  totals.nearExpiryConsumed = null;
  return {
    days, from, to,
    source: 'events',
    partial: true,
    totals, byDay,
    amount: null,
    amountReason: '未记录价格，无法计算金额',
    note: '该家庭尚未启用按日统计，本次仅按最近保留的 200 条操作估算；临期消耗无法还原。'
  };
}

const RECIPES = require('./recipes.json');

function nameHit(item, terms) {
  const names = [item.name, ...(item.names || [])].filter(Boolean).map(value => String(value).toLowerCase());
  return terms.some(term => {
    const target = String(term).toLowerCase();
    if (!target) return false;
    return names.some(name => target.length === 1 ? name === target : name.includes(target) || target.includes(name));
  });
}

function matchRecipes(recipes, items, options = {}) {
  const now = options.now || Date.now();
  const exclude = (options.exclude || []).map(value => String(value).trim()).filter(Boolean).slice(0, 10);
  const available = (items || []).filter(item => item.quantity > 0 && band(item.expiry, now) !== 'expired');
  const disliked = value => exclude.some(term => value === term || value.includes(term) || term.includes(value));
  const list = [];
  for (const recipe of recipes) {
    const main = recipe.main || [];
    if (!main.length) continue;
    if (main.some(need => (need.terms || [need.name]).some(disliked))) continue;
    const matched = [];
    const missing = [];
    for (const need of main) {
      const terms = need.terms && need.terms.length ? need.terms : [need.name];
      const item = available.find(candidate => nameHit(candidate, terms));
      if (!item) { missing.push(need.name); continue; }
      const state = band(item.expiry, now);
      matched.push({
        need: need.name, itemId: item.id, name: item.name,
        quantity: item.quantity, unit: item.unit, band: state,
        expiring: state === 'urgent' || state === 'soon'
      });
    }
    list.push({
      id: recipe.id, name: recipe.name, category: recipe.category,
      minutes: recipe.minutes, servings: recipe.servings,
      calories: recipe.calories, difficulty: recipe.difficulty,
      matched, missing, coverage: Math.round((matched.length / main.length) * 100) / 100,
      expiring: matched.filter(entry => entry.expiring).length,
      steps: recipe.steps, source: recipe.source, sourceUrl: recipe.sourceUrl
    });
  }
  list.sort((a, b) => a.missing.length - b.missing.length || b.matched.length - a.matched.length ||
    b.coverage - a.coverage || b.expiring - a.expiring || a.minutes - b.minutes || a.name.localeCompare(b.name, 'zh'));
  const ready = list.filter(entry => entry.missing.length === 0);
  // "Almost" must actually use something from the fridge; a 0/1 match is not almost.
  const almost = list.filter(entry => entry.missing.length === 1 && entry.matched.length > 0);
  const inspiration = list.filter(entry => entry.missing.length >= 2 || (entry.missing.length === 1 && entry.matched.length === 0)).slice(0, 20);
  return {
    ready,
    almost,
    inspiration,
    recipes: list,
    stats: { ready: ready.length, almost: almost.length, total: list.length },
    note: '来自 HowToCook 的真实菜谱库，按库存匹配，不生成新菜名；已排除过期批次，份量仅作参考。'
  };
}

function recipeList(home, data, now = Date.now()) {
  const servings = Number.isInteger(data && data.servings) && data.servings > 0 && data.servings <= 10 ? data.servings : 2;
  const items = (home.items || []).map(item => ({ ...item, names: [item.name, resolveAlias(home, item.name).name] }));
  const exclude = Array.isArray(data && data.exclude) ? data.exclude.filter(value => typeof value === 'string') : [];
  return { servings, ...matchRecipes(RECIPES, items, { now, exclude }) };
}

function todoList(home, now) {
  const groups = { expired: [], urgent: [], soon: [] };
  for (const item of home.items || []) {
    if (!(item.quantity > 0) || !item.expiry) continue;
    const state = band(item.expiry, now);
    if (!groups[state]) continue;
    groups[state].push({
      id: item.id, name: item.name, quantity: item.quantity, unit: item.unit,
      location: LOCATIONS.includes(item.location) ? item.location : '冷藏',
      expiry: item.expiry, band: state
    });
  }
  for (const list of Object.values(groups)) list.sort((a, b) => a.expiry.localeCompare(b.expiry));
  const shopping = (home.shopping || []).filter(item => !item.done).map(item => ({ id: item.id, name: item.name }));
  return {
    date: dayKey(now),
    counts: { expired: groups.expired.length, urgent: groups.urgent.length, soon: groups.soon.length, shopping: shopping.length },
    expired: groups.expired,
    urgent: groups.urgent,
    soon: groups.soon,
    shopping,
    note: '这是应用内待办，不是微信订阅消息；不会推送手机通知。'
  };
}

const ALIAS_LIMIT = 50;
const DEFAULT_SHELF_DAYS = { 冷藏: 7, 冷冻: 60, 常温: 3 };
const SHELF_LIFE = [
  { rule: '浆果', test: /草莓|蓝莓|树莓/, 冷藏: 3, 冷冻: 30, 常温: 2 },
  { rule: '叶菜', test: /菠菜|生菜|油菜|小白菜|青菜|香菜|韭菜|芹菜|空心菜/, 冷藏: 3, 冷冻: 30, 常温: 1 },
  { rule: '根茎', test: /土豆|马铃薯|胡萝卜|萝卜|红薯|山药|洋葱|南瓜|冬瓜/, 冷藏: 14, 冷冻: 60, 常温: 30 },
  { rule: '菌菇', test: /蘑菇|香菇|口蘑|金针菇|杏鲍菇|木耳/, 冷藏: 5, 冷冻: 30, 常温: 3 },
  { rule: '水果', test: /苹果|梨|橙|橘|柚|香蕉|葡萄|猕猴桃|西瓜|桃|芒果|菠萝/, 冷藏: 7, 冷冻: 60, 常温: 5 },
  { rule: '水产', test: /鱼|虾|蟹|贝|鱿鱼/, 冷藏: 1, 冷冻: 60, 常温: 1 },
  { rule: '肉类', test: /猪|牛|羊|鸡胸|鸡腿|肉|排骨|香肠/, 冷藏: 2, 冷冻: 90, 常温: 1 },
  { rule: '蛋', test: /鸡蛋|鸭蛋|鹅蛋|鹌鹑蛋/, 冷藏: 30, 冷冻: 60, 常温: 14 },
  { rule: '奶', test: /牛奶|酸奶|奶酪|奶油/, 冷藏: 7, 冷冻: 30, 常温: 1 },
  { rule: '豆制品', test: /豆腐|豆干|豆皮|腐竹/, 冷藏: 3, 冷冻: 30, 常温: 1 },
  { rule: '熟食', test: /熟食|卤味|剩菜|便当|凉菜/, 冷藏: 2, 冷冻: 30, 常温: 1 },
  { rule: '主食', test: /面包|馒头|米饭|面条|饺子|包子/, 冷藏: 3, 冷冻: 30, 常温: 2 }
];

// User-defined, family-scoped aliases. No built-in dictionary and no automatic learning:
// a wrong name is corrected only when the user explicitly configures it.
function aliasMap(home) {
  if (!home.aliases || typeof home.aliases !== 'object' || Array.isArray(home.aliases)) home.aliases = {};
  return home.aliases;
}

function aliasTarget(map, start, from) {
  let target = start;
  const seen = new Set([from]);
  for (let i = 0; i < 5; i++) {
    const entry = map[target];
    if (!entry) break;
    if (seen.has(target)) return null;
    seen.add(target);
    target = entry.to;
  }
  return target === from ? null : target;
}

function setAlias(home, from, to, now) {
  if (from === to) return null;
  const map = aliasMap(home);
  const target = aliasTarget(map, to, from);
  if (!target) return null;
  delete map[from];
  map[from] = { to: target, updatedAt: now };
  const keys = Object.keys(map);
  if (keys.length > ALIAS_LIMIT) {
    keys.sort((a, b) => (map[a].updatedAt || 0) - (map[b].updatedAt || 0));
    for (const key of keys.slice(0, keys.length - ALIAS_LIMIT)) delete map[key];
  }
  return { from, to: target };
}

function listAliases(home) {
  const map = home.aliases && typeof home.aliases === 'object' && !Array.isArray(home.aliases) ? home.aliases : {};
  return Object.entries(map)
    .map(([from, value]) => ({ from, to: value.to, updatedAt: value.updatedAt || 0 }))
    .sort((a, b) => b.updatedAt - a.updatedAt);
}

function removeAlias(home, from) {
  const map = home.aliases;
  if (!map || typeof map !== 'object' || !map[from]) return false;
  delete map[from];
  return true;
}

function resolveAlias(home, name) {
  const map = home.aliases && typeof home.aliases === 'object' && !Array.isArray(home.aliases) ? home.aliases : {};
  let current = name;
  const seen = new Set([current]);
  for (let i = 0; i < 5; i++) {
    const entry = map[current];
    if (!entry || !entry.to || seen.has(entry.to)) break;
    seen.add(entry.to);
    current = entry.to;
  }
  return current === name ? { name, aliasOf: '' } : { name: current, aliasOf: name };
}

function shelfDays(name, location) {
  const entry = SHELF_LIFE.find(rule => rule.test.test(name));
  const days = (entry && entry[location]) || DEFAULT_SHELF_DAYS[location] || DEFAULT_SHELF_DAYS['冷藏'];
  return { days, rule: entry ? entry.rule : '默认' };
}

function addDays(iso, days) {
  const stamp = new Date(iso + 'T00:00:00Z');
  stamp.setUTCDate(stamp.getUTCDate() + days);
  return stamp.toISOString().slice(0, 10);
}

// Only fills an empty expiry when the user picked "estimate"; an explicit date always wins.
function applyEstimate(item, now) {
  if (!item) return item;
  if (item.source !== 'estimate' || item.expiry) { delete item.estimateBasis; return item; }
  const { days, rule } = shelfDays(item.name, item.location);
  item.expiry = addDays(dayKey(now), days);
  item.estimateBasis = { days, rule, location: item.location };
  return item;
}

// Read-only comparison between a physical count and the current batches.
// It never writes: the client confirms each change through item.change/item.add.
function reconcile(home, entries, now = Date.now()) {
  const keyOf = (name, unit) => name + '\u0000' + unit;
  const inputs = new Map();
  for (const entry of entries) {
    const name = resolveAlias(home, entry.name).name;
    const key = keyOf(name, entry.unit);
    if (!inputs.has(key)) inputs.set(key, { name, unit: entry.unit, quantity: 0 });
    const bucket = inputs.get(key);
    bucket.quantity = Math.round((bucket.quantity + entry.quantity) * 1e6) / 1e6;
  }

  const batches = new Map();
  for (const item of (home.items || []).filter(row => row.quantity > 0)) {
    const name = resolveAlias(home, item.name).name;
    const key = keyOf(name, item.unit);
    if (!batches.has(key)) batches.set(key, { name, unit: item.unit, quantity: 0, items: [] });
    const group = batches.get(key);
    group.quantity = Math.round((group.quantity + item.quantity) * 1e6) / 1e6;
    group.items.push({
      itemId: item.id, name: item.name, quantity: item.quantity,
      location: item.location, expiry: item.expiry, band: band(item.expiry, now)
    });
  }

  const groups = [];
  const newGroups = [];
  for (const [key, input] of inputs) {
    const group = batches.get(key);
    if (!group) { newGroups.push({ name: input.name, unit: input.unit, inputQuantity: input.quantity }); continue; }
    const delta = Math.round((input.quantity - group.quantity) * 1e6) / 1e6;
    groups.push({
      name: input.name, unit: input.unit,
      inputQuantity: input.quantity, currentQuantity: group.quantity, delta,
      status: delta === 0 ? 'same' : delta > 0 ? 'more' : 'less',
      batches: group.items
    });
  }

  const unmentioned = [];
  for (const [key, group] of batches) {
    if (!inputs.has(key)) unmentioned.push({ name: group.name, unit: group.unit, quantity: group.quantity, batches: group.items });
  }
  const counts = { same: 0, more: 0, less: 0 };
  for (const group of groups) counts[group.status]++;
  return {
    summary: {
      inputs: inputs.size, matched: groups.length, new: newGroups.length,
      same: counts.same, more: counts.more, less: counts.less, unmentioned: unmentioned.length
    },
    groups,
    newGroups,
    unmentioned,
    note: '只做比对，不修改库存；确认后用 item.change 盘点，或用 item.add 新增批次。'
  };
}

exports.band = band;
exports.reconcile = reconcile;
exports.dayKey = dayKey;
exports.recordStats = recordStats;
exports.summarize = summarize;
exports.recipeList = recipeList;
exports.matchRecipes = matchRecipes;
exports.todoList = todoList;
exports.setAlias = setAlias;
exports.listAliases = listAliases;
exports.removeAlias = removeAlias;
exports.resolveAlias = resolveAlias;
exports.applyEstimate = applyEstimate;
exports.shelfDays = shelfDays;
exports.RECIPES = RECIPES;
exports.MAX_STATS_DAYS = MAX_STATS_DAYS;
exports.ALIAS_LIMIT = ALIAS_LIMIT;
exports.SHELF_LIFE = SHELF_LIFE;
