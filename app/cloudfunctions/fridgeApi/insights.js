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
  const from = dayKey(now - days * DAY);
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
      partial: Boolean(home.stats.since && home.stats.since > now - days * DAY),
      totals, byDay,
      amount: null,
      amountReason: '未记录价格，无法计算金额',
      note: '数量按单位分别统计，不跨单位换算；临期消耗指消耗时批次处于今天到期或 3 天内。'
    };
  }

  // Fallback: derive from the retained events (max 200) for homes that predate stats.
  const byDate = new Map();
  for (const event of home.events || []) {
    if (!event || typeof event.createdAt !== 'number' || event.createdAt < now - days * DAY) continue;
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
    for (const bucket of BUCKETS) if (entry[bucket]) addBucket(totals[bucket], entry[bucket]);
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

const RECIPES = [
  {
    id: 'tomato-egg', name: '番茄炒蛋', minutes: 15, servings: 2,
    needs: [{ name: '番茄', test: /番茄|西红柿/ }, { name: '鸡蛋', test: /鸡蛋|蛋/ }],
    steps: ['番茄洗净切块，鸡蛋打散。', '先把蛋液炒至凝固盛出，再炒软番茄。', '合锅翻炒调味，确保鸡蛋完全熟透。']
  },
  {
    id: 'broccoli-chicken', name: '西兰花炒鸡胸', minutes: 20, servings: 2,
    needs: [{ name: '西兰花', test: /西兰花/ }, { name: '鸡胸肉', test: /鸡胸|鸡肉/ }],
    steps: ['西兰花切小朵焯水，鸡胸肉切片。', '鸡肉另锅翻炒至变色。', '合锅调味，确保鸡肉中心熟透。']
  },
  {
    id: 'milk-oat', name: '牛奶燕麦粥', minutes: 10, servings: 1,
    needs: [{ name: '牛奶', test: /奶/ }, { name: '燕麦', test: /燕麦|麦片/ }],
    steps: ['按包装说明准备燕麦和牛奶。', '小火加热并持续搅拌，避免糊底。', '煮至燕麦熟软后盛出。']
  },
  {
    id: 'potato-pepper', name: '青椒土豆丝', minutes: 15, servings: 2,
    needs: [{ name: '土豆', test: /土豆|马铃薯/ }, { name: '青椒', test: /青椒|尖椒/ }],
    steps: ['土豆切丝后用清水冲去淀粉。', '热锅快炒土豆丝至断生。', '加入青椒丝调味，炒匀出锅。']
  },
  {
    id: 'mushroom-greens', name: '蘑菇炒青菜', minutes: 12, servings: 2,
    needs: [{ name: '蘑菇', test: /蘑菇|香菇|口蘑/ }, { name: '青菜', test: /青菜|生菜|菠菜|油菜|小白菜/ }],
    steps: ['蘑菇切片，青菜洗净沥干。', '先炒蘑菇至出水收干。', '加入青菜大火快炒，调味出锅。']
  },
  {
    id: 'carrot-egg', name: '胡萝卜炒蛋', minutes: 12, servings: 2,
    needs: [{ name: '胡萝卜', test: /胡萝卜/ }, { name: '鸡蛋', test: /鸡蛋|蛋/ }],
    steps: ['胡萝卜切丝，鸡蛋打散。', '先炒蛋盛出，再炒胡萝卜丝至变软。', '合锅翻炒调味，出锅。']
  },
  {
    id: 'cucumber-salad', name: '凉拌黄瓜', minutes: 8, servings: 2,
    needs: [{ name: '黄瓜', test: /黄瓜/ }],
    steps: ['黄瓜洗净拍碎切段。', '按口味加调味料拌匀。', '冷藏十分钟后口感更好。']
  },
  {
    id: 'fruit-yogurt', name: '水果酸奶杯', minutes: 5, servings: 1,
    needs: [{ name: '酸奶', test: /酸奶/ }, { name: '水果', test: /苹果|香蕉|草莓|蓝莓|猕猴桃|葡萄|橙/ }],
    steps: ['水果洗净切块。', '与酸奶分层装杯。', '现做现吃，避免久放。']
  }
];

function recipeList(home, data, now = Date.now()) {
  const servings = Number.isInteger(data && data.servings) && data.servings > 0 && data.servings <= 10 ? data.servings : 2;
  const available = (home.items || []).filter(item => item.quantity > 0 && band(item.expiry, now) !== 'expired');
  const list = RECIPES.map(recipe => {
    const matched = []; const missing = [];
    for (const need of recipe.needs) {
      const hit = available.find(item => need.test.test(item.name));
      if (hit) matched.push(need.name); else missing.push(need.name);
    }
    return {
      id: recipe.id, name: recipe.name, minutes: recipe.minutes, servings: recipe.servings,
      matched, missing, score: Math.round((matched.length / recipe.needs.length) * 100) / 100,
      steps: recipe.steps
    };
  });
  list.sort((a, b) => b.score - a.score || a.minutes - b.minutes);
  return {
    servings,
    recipes: list,
    note: '固定菜谱模板，不是 AI 生成；已排除过期批次，份量仅作参考、不自动换算用量。'
  };
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

exports.band = band;
exports.dayKey = dayKey;
exports.recordStats = recordStats;
exports.summarize = summarize;
exports.recipeList = recipeList;
exports.todoList = todoList;
exports.RECIPES = RECIPES;
exports.MAX_STATS_DAYS = MAX_STATS_DAYS;
