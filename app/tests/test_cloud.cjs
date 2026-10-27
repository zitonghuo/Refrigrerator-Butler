const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createService, POLICY } = require('../cloudfunctions/fridgeApi/service');
const { createStore } = require('../cloudfunctions/fridgeApi/store');

// Snapshot/rollback plus a transaction mutex reproduce the atomicity contract.
// These tests do NOT substitute for a real CloudBase transaction integration test.
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
function setup() {
  const store = new MemoryStore(); let now = Date.parse('2026-10-13T04:00:00Z'); let serial = 0;
  const service = createService(store, { clock: () => now, logger: false });
  const request = (who, action, data = {}, key = now + '-' + (++serial)) => service({ action, data, key }, { appid: 'test-app', openid: who });
  const ok = async (...args) => { const result = await request(...args); assert.equal(result.ok, true, JSON.stringify(result)); return result.data; };
  const login = who => ok(who, 'login', { policyVersion: POLICY });
  const home = async who => { await login(who); await ok(who, 'home.create', { name: who + '的厨房' }); return ok(who, 'snapshot'); };
  return { store, service, request, ok, login, home, advance: ms => { now += ms; }, key: () => now + '-' + (++serial) };
}
const food = { name: '番茄', quantity: '3', unit: '个', location: '冷藏', expiry: '2026-10-14', source: 'label' };

test('identity is server supplied; consent and login required', async () => {
  const f = setup();
  assert.equal((await f.service({ action: 'login', data: { openid: 'forged', policyVersion: POLICY } }, {})).error.code, 'UNAUTHENTICATED');
  assert.equal((await f.request('a', 'login', {})).error.code, 'CONSENT_REQUIRED');
  assert.equal((await f.request('a', 'snapshot')).error.code, 'UNAUTHENTICATED');
  const a = await f.login('a'); const b = await f.login('b'); assert.notEqual(a.user.id, b.user.id);
  assert.equal(JSON.stringify(a).includes('openid'), false);
  const restricted = createService(new MemoryStore(), { appId: 'expected-app', logger: false });
  assert.equal((await restricted({ action: 'session' }, { openid: 'a', appid: 'other-app' })).error.code, 'FORBIDDEN');
});
test('household isolation covers reads, writes, shopping and forged home IDs', async () => {
  const f = setup(); const a = await f.home('a'); await f.home('b');
  const added = await f.ok('a', 'item.add', { items: [food] });
  assert.equal((await f.request('b', 'item.get', { id: added.ids[0], homeId: a.home.id })).error.code, 'NOT_FOUND');
  assert.equal((await f.request('b', 'item.change', { id: added.ids[0], version: 1, kind: '消耗', quantity: 1 })).error.code, 'NOT_FOUND');
  const b = await f.ok('b', 'snapshot', { homeId: a.home.id }); assert.equal(b.items.length, 0);
  await f.ok('a', 'shopping.add', { name: '鸡蛋' }); const s = await f.ok('a', 'snapshot');
  assert.equal((await f.request('b', 'shopping.set', { id: s.shopping[0].id, version: 1, done: true })).error.code, 'NOT_FOUND');
});
test('atomic input validation and write retry idempotency', async () => {
  const f = setup(); await f.home('a'); const key = f.key();
  const first = await f.ok('a', 'item.add', { items: [food] }, key);
  const second = await f.ok('a', 'item.add', { items: [food] }, key); assert.deepEqual(first, second);
  assert.equal((await f.ok('a', 'snapshot')).items.length, 1);
  assert.equal((await f.request('a', 'item.add', { items: [{ ...food, name: '鸡蛋' }] }, key)).error.code, 'KEY_CONFLICT');
  assert.equal((await f.request('a', 'item.add', { items: [food, { ...food, quantity: -1 }] })).ok, false);
  assert.equal((await f.ok('a', 'snapshot')).items.length, 1);
  for (const quantity of [true, '', Infinity, -1, 0]) assert.equal((await f.request('a', 'item.add', { items: [{ ...food, quantity }] })).ok, false);
  assert.equal((await f.request('a', 'item.add', { items: [{ ...food, expiry: '2026-02-30' }] })).ok, false);
});
test('concurrent stock changes reject a stale version and never overdraw', async () => {
  const f = setup(); const s = await f.home('a'); await f.login('b'); await f.ok('b', 'home.join', { invite: s.home.invite });
  const { ids } = await f.ok('a', 'item.add', { items: [food] });
  const results = await Promise.all(['a', 'b'].map(u => f.request(u, 'item.change', { id: ids[0], version: 1, kind: '消耗', quantity: 2 })));
  assert.equal(results.filter(r => r.ok).length, 1); assert.equal(results.find(r => !r.ok).error.code, 'CONFLICT');
  const after = await f.ok('a', 'snapshot'); assert.equal(after.items[0].quantity, 1);
  await f.ok('a', 'item.change', { id: ids[0], version: 2, kind: '盘点', quantity: 0 }); assert.equal((await f.ok('a', 'snapshot')).items.length, 0);
});
test('invite expiry/revocation, owner checks, removal and permission withdrawal', async () => {
  const f = setup(); const s = await f.home('a'); const b = await f.login('b'); await f.login('c');
  await f.ok('b', 'home.join', { invite: s.home.invite });
  assert.equal((await f.ok('b', 'session')).home.invite, '');
  assert.equal((await f.request('b', 'home.rotate')).error.code, 'FORBIDDEN');
  await f.ok('a', 'home.removeMember', { memberId: b.user.id });
  assert.equal((await f.request('b', 'snapshot')).error.code, 'NO_HOME');
  assert.equal((await f.request('c', 'home.join', { invite: s.home.invite })).error.code, 'INVALID_INVITE');
  const fresh = await f.ok('a', 'session'); f.advance(8 * 86400000);
  assert.equal((await f.request('c', 'home.join', { invite: fresh.home.invite })).error.code, 'INVALID_INVITE');
});
test('owner transfer, leaving and deletion minimize retained personal data', async () => {
  const f = setup(); const s = await f.home('a'); const b = await f.login('b'); await f.ok('b', 'home.join', { invite: s.home.invite });
  assert.equal((await f.request('a', 'account.delete')).error.code, 'TRANSFER_REQUIRED');
  await f.ok('a', 'profile.update', { name: '测试本人' }); await f.ok('a', 'item.add', { items: [food] });
  await f.ok('a', 'home.transfer', { memberId: b.user.id }); await f.ok('a', 'home.leave');
  const after = await f.ok('b', 'snapshot'); assert.equal(after.events[0].actor, '已离开成员');
  const deletionKey = f.key();
  await f.ok('a', 'account.delete', {}, deletionKey);
  await f.ok('a', 'account.delete', {}, deletionKey);
  assert.equal((await f.request('a', 'session')).error.code, 'UNAUTHENTICATED');
  await f.ok('b', 'account.delete');
  assert.equal([...f.store.data.keys()].filter(k => k.startsWith('fridge_homes/')).length, 0);
  assert.equal([...f.store.data.keys()].filter(k => k.startsWith('fridge_invites/')).length, 0);
});
test('stale requests cannot be replayed after receipt retention; usage rate bounded', async () => {
  const f = setup(); await f.home('a'); const key = f.key();
  await f.ok('a', 'shopping.add', { name: '牛奶' }, key); f.advance(25 * 3600000);
  assert.equal((await f.request('a', 'shopping.add', { name: '牛奶' }, key)).error.code, 'EXPIRED_REQUEST');
  let limited = false; for (let i = 0; i < 102; i++) { const r = await f.request('a', 'session'); if (!r.ok) { assert.equal(r.error.code, 'RATE_LIMITED'); limited = true; break; } }
  assert.equal(limited, true);
});
test('CloudBase adapter removes _id and preserves returned transaction values', async () => {
  const saved = []; const db = { runTransaction: async fn => fn({ collection: c => ({ doc: id => ({
    get: async () => ({ data: id === 'missing' ? null : { _id: id, name: 'x' } }),
    set: async arg => saved.push({ c, id, arg }), remove: async () => saved.push('removed')
  }) }) }) };
  const store = createStore(db);
  assert.equal(await store.transaction(async tx => { assert.equal(await tx.get('a', 'missing'), null); await tx.put('a', 'one', { _id: 'one', name: 'x' }); return 42; }), 42);
  assert.deepEqual(saved[0].arg, { data: { name: 'x' } });
});
