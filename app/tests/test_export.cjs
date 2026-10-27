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

function setup(start = Date.parse('2026-10-24T02:00:00Z')) {
  const store = new MemoryStore(); let now = start; let serial = 0;
  const service = createService(store, { clock: () => now, logger: false });
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

const food = { name: '番茄', quantity: 2, unit: '个', location: '冷藏', expiry: '2026-10-30', source: 'manual' };

test('export returns the household data without invite code or identity secrets', async () => {
  const f = setup(); const snapshot = await f.home('a');
  await f.write('a', 'profile.update', { name: '测试甲' });
  await f.write('a', 'item.add', { items: [food] });
  await f.write('a', 'shopping.add', { name: '鸡蛋' });
  const before = await f.read('a', 'snapshot');
  await f.write('a', 'item.change', { id: before.items[0].id, version: 1, kind: '消耗', quantity: 1 });

  const data = await f.read('a', 'account.export');
  assert.equal(data.schemaVersion, '1.0');
  assert.match(data.exportedAt, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(data.user.name, '测试甲');
  assert.equal(data.home.name, 'a的厨房');
  assert.equal(data.home.members.length, 1);
  assert.equal(data.home.members[0].name, '测试甲');
  assert.equal(data.items.length, 1);
  assert.equal(data.items[0].name, '番茄');
  assert.equal(data.shopping.length, 1);
  assert.ok(data.events.length >= 2);
  assert.ok(data.stats && data.stats.days, '导出应包含按日统计');
  assert.equal(Object.hasOwn(data.home, 'invite'), false);
  assert.equal(JSON.stringify(data).includes(snapshot.home.invite), false);
  assert.equal(JSON.stringify(data).includes('openid'), false);
});

test('export is read-only, needs no idempotency key, and stays inside the household', async () => {
  const f = setup(); await f.home('a'); await f.home('b');
  await f.write('a', 'item.add', { items: [food] });
  const exported = await f.read('b', 'account.export'); // no key
  assert.equal(exported.home.name, 'b的厨房');
  assert.equal(exported.items.length, 0);
  assert.equal(JSON.stringify(exported).includes('番茄'), false);
});

test('export requires a household', async () => {
  const f = setup();
  await f.write('a', 'login', { policyVersion: POLICY });
  const result = await f.call('a', 'account.export');
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'NO_HOME');
});
