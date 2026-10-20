const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function setup() {
  const storage = new Map(); const calls = []; const routes = []; const app = { globalData: { session: { user: { id: 'a', homeId: 'h' }, home: { id: 'h' } } } };
  let transport = async () => ({ result: { ok: true, data: {} } });
  const wx = { getStorageSync: k => storage.get(k), setStorageSync: (k, v) => storage.set(k, structuredClone(v)), removeStorageSync: k => storage.delete(k),
    reLaunch: args => routes.push(args.url), stopPullDownRefresh() {},
    cloud: { callFunction: async args => { calls.push(structuredClone(args)); return transport(args); } } };
  const module = { exports: {} };
  const source = fs.readFileSync(path.join(__dirname, '../miniprogram/utils/api.js'), 'utf8');
  vm.runInNewContext(source, { module, require: () => ({ cloudEnv: 'test-env', functionName: 'fridgeApi', policyVersion: '2026-10-13' }), getApp: () => app, wx, Date, Math });
  return { api: module.exports, storage, calls, routes, app, transport: fn => { transport = fn; } };
}
test('network ambiguity survives reload and retry keeps exact operation key', async () => {
  const f = setup(); f.transport(async () => { throw Error('timeout'); });
  await assert.rejects(f.api.write('item.add', { items: [{ name: '番茄' }] }), e => e.code === 'NETWORK');
  assert.equal(f.api.hasPending(), true); const key = f.calls[0].data.key;
  await assert.rejects(f.api.write('shopping.add', { name: '鸡蛋' }), e => e.code === 'PENDING'); assert.equal(f.calls.length, 1);
  f.transport(async () => ({ result: { ok: true, data: { ids: ['x'] } } }));
  assert.equal(await f.api.resume(), 'item.add'); assert.equal(f.calls[1].data.key, key); assert.equal(f.api.hasPending(), false);
});
test('definite validation rejection clears pending request for correction', async () => {
  const f = setup(); f.transport(async () => ({ result: { ok: false, error: { code: 'INVALID', message: 'bad input' } } }));
  await assert.rejects(f.api.write('item.add', { items: [] }), e => e.code === 'INVALID'); assert.equal(f.api.hasPending(), false);
});
test('consent gate stops server calls; no-home routes to onboarding', async () => {
  const f = setup(); assert.equal(await f.api.ensure(), false); assert.equal(f.calls.length, 0); assert.equal(f.routes[0], '/pages/login/login');
  f.storage.set('consent-v2', '2026-10-13'); f.transport(async () => ({ result: { ok: true, data: { user: { id: 'a' }, home: null } } }));
  assert.equal(await f.api.ensure(), false); assert.equal(f.routes[1], '/pages/onboarding/onboarding');
});
test('pending state scoped per account and logout clears local food draft', async () => {
  const f = setup(); f.storage.set('pending-v2-other', { action: 'item.add' }); f.storage.set('add-draft-v2', { name: 'private' });
  assert.equal(f.api.hasPending(), false); f.api.clearLocal(); assert.equal(f.storage.has('add-draft-v2'), false); assert.equal(f.app.globalData.session, null);
});
test('cold start reconciles an account deletion whose response was lost', async () => {
  const f = setup(); f.app.globalData.session = null;
  f.storage.set('consent-v2', '2026-10-13'); f.storage.set('last-user-v2', 'a');
  f.storage.set('pending-v2-a', { action: 'account.delete', data: {}, key: 'old' });
  f.transport(async () => ({ result: { ok: false, error: { code: 'UNAUTHENTICATED', message: 'no account' } } }));
  assert.equal(await f.api.ensure(false), false);
  assert.equal(f.storage.has('pending-v2-a'), false); assert.equal(f.storage.has('last-user-v2'), false);
});
