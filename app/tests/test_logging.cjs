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
  const entries = [];
  const service = createService(store, { clock: () => now, logger: entry => entries.push(entry) });
  const call = (who, action, data = {}, key) => service({ action, data, ...(key === undefined ? {} : { key }) }, { appid: 'test-app', openid: who });
  const write = (who, action, data = {}) => call(who, action, data, now + '-' + (++serial));
  return { store, entries, call, write, clock: () => now };
}

test('successful calls log action, code, duration and timestamp only', async () => {
  const f = setup();
  await f.write('a', 'login', { policyVersion: POLICY });
  assert.equal(f.entries.length, 1);
  const [entry] = f.entries;
  assert.equal(entry.action, 'login');
  assert.equal(entry.ok, true);
  assert.equal(entry.code, 'OK');
  assert.equal(typeof entry.ms, 'number');
  assert.match(entry.ts, /^\d{4}-\d{2}-\d{2}T/);
  assert.deepEqual(Object.keys(entry).sort(), ['action', 'code', 'ms', 'ok', 'ts']);
});

test('failures log their error code', async () => {
  const f = setup();
  await f.write('a', 'login', { policyVersion: POLICY });
  await f.write('a', 'home.create', { name: '测试厨房' });
  const result = await f.write('a', 'item.change', { id: 'missing', version: 1, kind: '消耗', quantity: 1 });
  assert.equal(result.ok, false);
  const last = f.entries[f.entries.length - 1];
  assert.equal(last.ok, false);
  assert.equal(last.code, 'NOT_FOUND');
  assert.equal(last.action, 'item.change');
});

test('logs never contain OpenID, household names or invite codes', async () => {
  const f = setup();
  await f.write('alice-openid', 'login', { policyVersion: POLICY });
  await f.write('alice-openid', 'home.create', { name: '秘密厨房' });
  await f.write('alice-openid', 'item.add', { items: [{ name: '秘密食材', quantity: 1, unit: '个', location: '冷藏', expiry: '', source: 'manual' }] });
  const serialized = JSON.stringify(f.entries);
  assert.equal(serialized.includes('alice-openid'), false);
  assert.equal(serialized.includes('秘密厨房'), false);
  assert.equal(serialized.includes('秘密食材'), false);
  assert.equal(f.entries.every(entry => entry.action && entry.code && typeof entry.ms === 'number'), true);
});

test('logging can be disabled for tests and tooling', async () => {
  const service = createService(new MemoryStore(), { clock: () => Date.now(), logger: false });
  const result = await service({ action: 'session', data: {} }, { appid: 'app', openid: 'a' });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, 'UNAUTHENTICATED');
});
