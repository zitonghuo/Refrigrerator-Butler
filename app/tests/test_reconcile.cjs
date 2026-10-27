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
  const service = createService(store, { clock: () => now, logger: false });
  const call = (who, action, data = {}, key) => service({ action, data, ...(key === undefined ? {} : { key }) }, { appid: 'test-app', openid: who });
  const read = async (who, action, data = {}, key) => {
    const result = await call(who, action, data, key);
    assert.equal(result.ok, true, JSON.stringify(result));
    return result.data;
  };
  const write = (who, action, data = {}) => read(who, action, data, now + '-' + (++serial));
  const home = async who => { await write(who, 'login', { policyVersion: POLICY }); await write(who, 'home.create', { name: who + '的厨房' }); };
  return { store, call, read, write, home };
}

const item = (over = {}) => ({ name: '番茄', quantity: 2, unit: '个', location: '冷藏', expiry: '', source: 'manual', ...over });

test('reconcile compares counts, finds new items and keeps unmentioned batches', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [item({ name: '番茄', quantity: 2 }), item({ name: '鸡蛋', quantity: 5 })] });
  const before = await f.read('a', 'snapshot');

  const result = await f.read('a', 'inventory.reconcile', { items: [
    { name: '番茄', unit: '个', quantity: 3 },
    { name: '牛奶', unit: '盒', quantity: 2 }
  ] });
  assert.deepEqual(result.summary, { inputs: 2, matched: 1, new: 1, same: 0, more: 1, less: 0, unmentioned: 1 });
  const tomato = result.groups.find(x => x.name === '番茄');
  assert.equal(tomato.delta, 1);
  assert.equal(tomato.status, 'more');
  assert.equal(tomato.batches.length, 1);
  assert.deepEqual(result.newGroups.map(x => x.name), ['牛奶']);
  assert.deepEqual(result.unmentioned.map(x => x.name), ['鸡蛋']);

  const after = await f.read('a', 'snapshot');
  assert.equal(after.revision, before.revision, 'reconcile must not modify the home');
  assert.equal(after.items.find(x => x.name === '番茄').quantity, 2);
});

test('reconcile applies family aliases and separates units', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'alias.set', { from: '番茄', to: '西红柿' });
  await f.write('a', 'item.add', { items: [
    item({ name: '西红柿', quantity: 2, unit: '个' }),
    item({ name: '西红柿', quantity: 300, unit: '克' })
  ] });
  const result = await f.read('a', 'inventory.reconcile', { items: [
    { name: '番茄', unit: '个', quantity: 2 }
  ] });
  assert.equal(result.groups.length, 1);
  assert.equal(result.groups[0].name, '西红柿');
  assert.equal(result.groups[0].status, 'same');
  assert.equal(result.unmentioned.length, 1);
  assert.equal(result.unmentioned[0].unit, '克');
});

test('duplicate input rows for the same name and unit are summed', async () => {
  const f = setup(); await f.home('a');
  await f.write('a', 'item.add', { items: [item({ name: '番茄', quantity: 2 })] });
  const result = await f.read('a', 'inventory.reconcile', { items: [
    { name: '番茄', unit: '个', quantity: 1 },
    { name: '番茄', unit: '个', quantity: 2 }
  ] });
  assert.equal(result.summary.inputs, 1);
  assert.equal(result.groups[0].inputQuantity, 3);
  assert.equal(result.groups[0].delta, 1);
});

test('reconcile validates input and requires a household', async () => {
  const f = setup();
  await f.write('a', 'login', { policyVersion: POLICY });
  assert.equal((await f.call('a', 'inventory.reconcile', { items: [{ name: '番茄', unit: '个', quantity: 1 }] })).error.code, 'NO_HOME');

  await f.home('b');
  assert.equal((await f.call('b', 'inventory.reconcile', { items: [] })).error.code, 'INVALID');
  const tooMany = Array.from({ length: 51 }, () => ({ name: '番茄', unit: '个', quantity: 1 }));
  assert.equal((await f.call('b', 'inventory.reconcile', { items: tooMany })).error.code, 'INVALID');
  assert.equal((await f.call('b', 'inventory.reconcile', { items: [{ name: '番茄', unit: '个', quantity: -1 }] })).error.code, 'INVALID');
});
