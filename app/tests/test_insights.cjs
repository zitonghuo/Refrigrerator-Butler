const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createService, POLICY } = require('../cloudfunctions/fridgeApi/service');

// Same in-memory transaction model as test_cloud.cjs: it reproduces atomicity,
// but is not a substitute for a real CloudBase integration test.
class MemoryStore {
  constructor() { this.data = new Map(); this.tail = Promise.resolve(); }
  transaction(run) {
    const task = this.tail.then(async () => {
      const draft = structuredClone(this.data);
      const result = await run({
        get: async (c, id) => structuredClone(draft.get(c + '/' + id) || null),
        put: async (c, id, data) => draft.set(c + '/' + id, structuredClone(data)),
        remove: async (c, id) => draft.delete(c + '/' + id)
      });
      this.data = draft; return result;
    });
    this.tail = task.catch(() => {}); return task;
  }
}

function setup(start = Date.parse('2026-10-20T02:00:00Z')) { // 10:00 Asia/Shanghai
  const store = new MemoryStore(); let now = start; let serial = 0;
  const service = createService(store, { clock: () => now });
  const call = (who, action, data = {}, key) => service({ action, data, ...(key === undefined ? {} : { key }) }, { appid: 'test-app', openid: who });
  const read = async (who, action, data = {}, key) => {
    const result = await call(who, action, data, key);
    assert.equal(result.ok, true, JSON.stringify(result));
    return result.data;
  };
  const write = async (who, action, data = {}) => read(who, action, data, now + '-' + (++serial));
  const login = who => write(who, 'login', { policyVersion: POLICY });
  const home = async who => { await login(who); await write(who, 'home.create', { name: who + '的厨房' }); return read(who, 'snapshot'); };
  return { store, service, call, read, write, login, home, advance: ms => { now += ms; }, now: () => now };
}

const item = (over = {}) => ({ name: '番茄', quantity: 1, unit: '个', location: '冷藏', expiry: '', source: 'manual', ...over });

test('report aggregates daily stats by unit and keeps units separate', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [item({ quantity: 3, expiry: '2026-10-22', name: '番茄' })] });
  await f.write('a', 'item.add', { items: [item({ quantity: 2, unit: '盒', name: '牛奶' })] });
  let snapshot = await f.read('a', 'snapshot');
  const tomato = snapshot.items.find(x => x.name === '番茄');
  const milk = snapshot.items.find(x => x.name === '牛奶');
  await f.write('a', 'item.change', { id: tomato.id, version: 1, kind: '消耗', quantity: 1 });
  await f.write('a', 'item.change', { id: milk.id, version: 1, kind: '丢弃', quantity: 1 });
  snapshot = await f.read('a', 'snapshot');
  const remaining = snapshot.items.find(x => x.name === '番茄');
  await f.write('a', 'item.change', { id: remaining.id, version: 2, kind: '盘点', quantity: 1 });

  const report = await f.read('a', 'report.summary', { days: 7 });
  assert.equal(report.days, 7);
  assert.equal(report.from,'2026-10-14');
  assert.equal(report.to,'2026-10-20');
  assert.equal(report.source, 'stats');
  assert.equal(report.byDay.length, 1);
  assert.deepEqual(report.totals.in, { count: 2, units: { '个': 3, '盒': 2 } });
  assert.deepEqual(report.totals.consume, { count: 1, units: { '个': 1 } });
  assert.deepEqual(report.totals.discard, { count: 1, units: { '盒': 1 } });
  assert.deepEqual(report.totals.adjust, { count: 1, units: { '个': -1 } });
  assert.equal(report.amount, null);
  assert.match(report.amountReason, /价格/);
  // A home younger than the window is reported as partial instead of hiding the gap.
  assert.equal(report.partial, true);
});

test('near-expiry consumption is counted only while the batch is in the 3-day window', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [
    item({ quantity: 2, name: '临期番茄', expiry: '2026-10-22' }),
    item({ quantity: 2, name: '远期黄瓜', expiry: '2026-10-30' })
  ] });
  const snapshot = await f.read('a', 'snapshot');
  for (const target of snapshot.items) {
    await f.write('a', 'item.change', { id: target.id, version: 1, kind: '消耗', quantity: 1 });
  }
  const report = await f.read('a', 'report.summary', { days: 7 });
  assert.deepEqual(report.totals.nearExpiryConsumed, { count: 1, units: { '个': 1 } });
});

test('report falls back to retained events when a home predates daily stats', async () => {
  const f = setup(); const snapshot = await f.home('a');
  await f.write('a', 'item.add', { items: [item({ quantity: 2 })] });
  const stored = f.store.data.get('fridge_homes/' + snapshot.home.id);
  delete stored.stats;
  f.store.data.set('fridge_homes/' + snapshot.home.id, stored);

  const report = await f.read('a', 'report.summary', { days: 7 });
  assert.equal(report.source, 'events');
  assert.deepEqual(report.byDay[0].in,{count:1,units:{'个':2}});
  assert.equal(report.partial, true);
  assert.deepEqual(report.totals.in, { count: 1, units: { '个': 2 } });
  assert.equal(report.totals.nearExpiryConsumed, null);
  assert.match(report.note, /200 条/);
});

test('daily stats are pruned to a rolling 60-day window', async () => {
  const f = setup(); const snapshot = await f.home('a');
  await f.write('a', 'item.add', { items: [item({ quantity: 1 })] });
  f.advance(70 * 86400000);
  await f.write('a', 'item.add', { items: [item({ quantity: 1 })] });
  const home = f.store.data.get('fridge_homes/' + snapshot.home.id);
  assert.deepEqual(Object.keys(home.stats.days).sort(), ['2026-12-29']);
  assert.equal(home.stats.days['2026-10-20'], undefined);
});

test('recipes match in-stock items, exclude expired batches and stay sorted', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [
    item({ name: '番茄', quantity: 2, expiry: '2026-10-23' }),
    item({ name: '鸡蛋', quantity: 3, unit: '个', expiry: '2026-10-27' }),
    item({ name: '西兰花', quantity: 1, unit: '颗', expiry: '2026-10-19' })
  ] });
  const result = await f.read('a', 'recipe.list', { servings: 3 });
  assert.equal(result.servings, 3);
  assert.equal(result.recipes.length, 8);
  const tomatoEgg = result.recipes.find(x => x.id === 'tomato-egg');
  assert.deepEqual(tomatoEgg.matched, ['番茄', '鸡蛋']);
  assert.equal(tomatoEgg.score, 1);
  const broccoli = result.recipes.find(x => x.id === 'broccoli-chicken');
  assert.equal(broccoli.score, 0, '西兰花已过期，不应参与匹配');
  assert.ok(result.recipes[0].score >= result.recipes[result.recipes.length - 1].score);
  assert.match(result.note, /不是 AI/);
});

test('daily todos list expiring batches and open shopping items only', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [
    item({ name: '过期苹果', quantity: 1, expiry: '2026-10-19' }),
    item({ name: '今天到期牛奶', quantity: 1, unit: '盒', expiry: '2026-10-20' }),
    item({ name: '下周黄瓜', quantity: 1, expiry: '2026-10-28' })
  ] });
  await f.write('a', 'shopping.add', { name: '鸡蛋' });
  await f.write('a', 'shopping.add', { name: '面粉' });
  const snapshot = await f.read('a', 'snapshot');
  await f.write('a', 'shopping.set', { id: snapshot.shopping[0].id, version: 1, done: true });

  const todo = await f.read('a', 'todo.list');
  assert.deepEqual(todo.counts, { expired: 1, urgent: 1, soon: 0, shopping: 1 });
  assert.equal(todo.expired[0].name, '过期苹果');
  assert.equal(todo.urgent[0].name, '今天到期牛奶');
  assert.deepEqual(todo.shopping.map(x => x.name), ['鸡蛋']);
  assert.match(todo.note, /不是微信订阅消息/);
});

test('insight actions require a home and are read-only (no idempotency key needed)', async () => {
  const f = setup();
  await f.login('a');
  for (const action of ['report.summary', 'recipe.list', 'todo.list']) {
    const result = await f.call('a', action);
    assert.equal(result.ok, false);
    assert.equal(result.error.code, 'NO_HOME');
  }
  await f.home('a');
  assert.equal((await f.read('a', 'report.summary')).days, 7);
});
