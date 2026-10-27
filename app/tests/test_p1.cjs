const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createService, POLICY } = require('../cloudfunctions/fridgeApi/service');

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

function setup(start = Date.parse('2026-10-27T02:00:00Z')) {
  const store = new MemoryStore(); let now = start; let serial = 0;
  const service = createService(store, { clock: () => now });
  const call = (who, action, data = {}, key) => service({ action, data, ...(key === undefined ? {} : { key }) }, { appid: 'test-app', openid: who });
  const read = async (who, action, data = {}, key) => {
    const result = await call(who, action, data, key);
    assert.equal(result.ok, true, JSON.stringify(result));
    return result.data;
  };
  const write = (who, action, data = {}) => read(who, action, data, now + '-' + (++serial));
  const home = async who => {
    await write(who, 'login', { policyVersion: POLICY });
    await write(who, 'home.create', { name: who + '的厨房' });
    return read(who, 'snapshot');
  };
  return { store, call, read, write, home, advance: ms => { now += ms; } };
}

const item = (over = {}) => ({ name: '番茄', quantity: 1, unit: '个', location: '冷藏', expiry: '', source: 'manual', ...over });
const daysFrom = (iso, days) => {
  const stamp = new Date(iso + 'T00:00:00Z');
  stamp.setUTCDate(stamp.getUTCDate() + days);
  return stamp.toISOString().slice(0, 10);
};

test('a user-defined alias rewrites new batches and keeps the original name', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'alias.set', { from: '番茄', to: '西红柿' });
  await f.write('a', 'item.add', { items: [item({ name: '番茄' })] });
  const snapshot = await f.read('a', 'snapshot');
  assert.equal(snapshot.items[0].name, '西红柿');
  assert.equal(snapshot.items[0].aliasOf, '番茄');
});

test('alias chains resolve to the final name and cycles are rejected', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'alias.set', { from: '番茄', to: '西红柿' });
  await f.write('a', 'alias.set', { from: '西红柿', to: '番茄大' });
  await f.write('a', 'item.add', { items: [item({ name: '番茄' })] });
  const snapshot = await f.read('a', 'snapshot');
  assert.equal(snapshot.items[0].name, '番茄大');
  assert.equal(snapshot.items[0].aliasOf, '番茄');

  const cycle = await f.write('a', 'alias.set', { from: '番茄大', to: '番茄' })
    .then(() => 'unexpected')
    .catch(() => 'rejected');
  assert.equal(cycle, 'rejected');
});

test('aliases can be listed and removed, and stay inside their household', async () => {
  const f = setup(); await f.home('a'); await f.home('b');
  await f.write('a', 'alias.set', { from: '番茄', to: '西红柿' });
  const listed = await f.read('a', 'alias.list');
  assert.deepEqual(listed.items.map(x => [x.from, x.to]), [['番茄', '西红柿']]);
  assert.equal(listed.limit, 50);
  assert.deepEqual((await f.read('b', 'alias.list')).items, []);

  await f.write('a', 'alias.remove', { from: '番茄' });
  assert.deepEqual((await f.read('a', 'alias.list')).items, []);
  await f.write('a', 'item.add', { items: [item({ name: '番茄' })] });
  const snapshot = await f.read('a', 'snapshot');
  assert.equal(snapshot.items[0].name, '番茄');
  assert.equal(snapshot.items[0].aliasOf, undefined);
});

test('alias count is capped at 50 entries, evicting the oldest update', async () => {
  const f = setup(); await f.home('a');
  for (let i = 0; i < 51; i++) await f.write('a', 'alias.set', { from: '食材' + i, to: '规范' + i });
  const listed = await f.read('a', 'alias.list');
  assert.equal(listed.items.length, 50);
  assert.equal(listed.items.some(x => x.from === '食材0'), false);
});

test('rejects an alias pointing at itself', async () => {
  const f = setup(); await f.home('a');
  const result = await f.call('a', 'alias.set', { from: '番茄', to: '番茄' }, Date.parse('2026-10-27T02:00:00Z') + '-self');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'INVALID');
});

test('export includes user-defined aliases', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'alias.set', { from: '番茄', to: '西红柿' });
  const data = await f.read('a', 'account.export');
  assert.deepEqual(data.aliases.map(x => [x.from, x.to]), [['番茄', '西红柿']]);
});

test('estimated expiry uses the reference table when the date is empty', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [item({ name: '菠菜', quantity: 1, unit: '把', source: 'estimate' })] });
  const snapshot = await f.read('a', 'snapshot');
  assert.equal(snapshot.items[0].expiry, daysFrom('2026-10-27', 3));
  assert.deepEqual(snapshot.items[0].estimateBasis, { days: 3, rule: '叶菜', location: '冷藏' });
});

test('an explicit date always wins over estimation', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [item({ name: '牛奶', unit: '盒', source: 'estimate', expiry: '2026-11-05' })] });
  const snapshot = await f.read('a', 'snapshot');
  assert.equal(snapshot.items[0].expiry, '2026-11-05');
  assert.equal(snapshot.items[0].estimateBasis, undefined);
});

test('unknown food falls back to the default shelf life, manual dates are untouched', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [
    item({ name: '神秘食材', source: 'estimate' }),
    item({ name: '手动食材', source: 'manual', expiry: '' })
  ] });
  const snapshot = await f.read('a', 'snapshot');
  const estimated = snapshot.items.find(x => x.name === '神秘食材');
  const manual = snapshot.items.find(x => x.name === '手动食材');
  assert.equal(estimated.expiry, daysFrom('2026-10-27', 7));
  assert.deepEqual(estimated.estimateBasis, { days: 7, rule: '默认', location: '冷藏' });
  assert.equal(manual.expiry, '');
  assert.equal(manual.estimateBasis, undefined);
});

test('updating a batch can trigger or clear estimation', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [item({ name: '鸡胸肉', unit: '袋', location: '冷冻' })] });
  let snapshot = await f.read('a', 'snapshot');
  const id = snapshot.items[0].id;
  await f.write('a', 'item.update', { id, version: 1, name: '鸡胸肉', unit: '袋', location: '冷冻', expiry: '', source: 'estimate' });
  snapshot = await f.read('a', 'snapshot');
  assert.equal(snapshot.items[0].expiry, daysFrom('2026-10-27', 90));
  assert.equal(snapshot.items[0].estimateBasis.rule, '肉类');

  await f.write('a', 'item.update', { id, version: 2, name: '鸡胸肉', unit: '袋', location: '冷冻', expiry: '', source: 'manual' });
  snapshot = await f.read('a', 'snapshot');
  assert.equal(snapshot.items[0].estimateBasis, undefined);
});
