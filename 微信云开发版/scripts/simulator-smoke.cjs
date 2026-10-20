const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Connection = require('miniprogram-automator/out/Connection').default;
const config = require('../miniprogram/config');
// This script uses the DevTools automation protocol with synthetic render data.
// No configured cloud environment is allowed; no user inventory is written.
if (config.cloudEnv) throw Error('Run fixture rendering against an unconfigured test copy only.');
const root = path.join(__dirname, '..');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const c = await Connection.create(process.env.WECHAT_AUTOMATION_WS || 'ws://127.0.0.1:9420');
  const folder = path.join(root, 'test-results/simulator'); fs.mkdirSync(folder, { recursive: true });
  async function wx(method, ...args) { return (await c.send('App.callWxMethod', { method, args })).result; }
  async function route(method, url) {
    await wx(method, { url });
    for (let attempt = 0; attempt < 30; attempt++) {
      const p = await c.send('App.getCurrentPage');
      if (p.path === url.split('?')[0].slice(1)) { await sleep(300); return p.pageId; }
      await sleep(100);
    }
    throw Error('Unexpected page after ' + url);
  }
  async function shot(file, id, data) {
    if (data) await c.send('Page.setData', { pageId: id, data });
    await sleep(350);
    const result = await c.send('App.captureScreenshot');
    fs.writeFileSync(path.join(folder, file + '.png'), Buffer.from(result.data, 'base64'));
    console.log('Rendered ' + file);
  }
  const old = await wx('getStorageSync', 'consent-v2');
  try {
    const info = await wx('getSystemInfoSync'); console.log('Simulator base library: ' + info.SDKVersion);
    let id = await route('reLaunch', '/pages/login/login');
    const login = await c.send('Page.getData', { pageId: id }); assert.equal(login.data.name, '小满冰箱');
    await shot('01-login', id);
    await wx('setStorageSync', 'consent-v2', config.policyVersion);
    const items = [
      { id: 'fixture-a', name: '番茄（测试）', quantity: 3, unit: '个', location: '冷藏', expiry: '2026-10-14', band: 'soon', label: '3 天内' },
      { id: 'fixture-b', name: '鸡胸肉（测试）', quantity: 2, unit: '袋', location: '冷冻', expiry: '2026-11-01', band: 'fresh', label: '7 天以上' }
    ];
    id = await route('switchTab', '/pages/home/home');
    await shot('02-home-fixture', id, { error: '', loading: false, home: { name: '测试家庭 · 示例数据' }, items, visible: items,
      zones: [{ name: '全部', count: 2 }, { name: '冷藏', count: 1 }, { name: '冷冻', count: 1 }, { name: '常温', count: 0 }], urgent: 1, expired: 0, pending: 2 });
    await c.send('Page.callMethod', { pageId: id, method: 'search', args: [{ detail: { value: '番茄' } }] });
    assert.equal((await c.send('Page.getData', { pageId: id })).data.visible.length, 1);
    id = await route('navigateTo', '/pages/add/add');
    await shot('03-add', id, { error: '', loading: false });
    id = await route('navigateTo', '/pages/detail/detail?id=fixture-a');
    await shot('04-detail-fixture', id, { error: '', loading: false, item: items[0], form: items[0], events: [] });
    id = await route('switchTab', '/pages/shopping/shopping');
    await shot('05-shopping-fixture', id, { error: '', loading: false, pending: 1, items: [{ id: 's1', name: '鸡蛋（测试）', done: false, version: 1 }, { id: 's2', name: '燕麦（测试）', done: true, version: 1 }] });
    id = await route('switchTab', '/pages/family/family');
    await shot('06-family-fixture', id, { error: '', loading: false, user: { id: 'a' }, home: { name: '测试家庭 · 示例数据', isOwner: true, ownerId: 'a', members: [{ id: 'a', name: '测试成员甲' }, { id: 'b', name: '测试成员乙' }], invite: 'TEST-NOT-A-REAL-CODE' }, expiry: '测试有效期' });
    id = await route('switchTab', '/pages/profile/profile');
    await shot('07-profile-fixture', id, { error: '', loading: false, name: '测试成员甲', user: { id: 'a' }, home: { name: '测试家庭' } });
    id = await route('navigateTo', '/pages/privacy/privacy'); await shot('08-privacy', id);
    fs.writeFileSync(path.join(folder, 'result.json'), JSON.stringify({ passed: true, kind: 'real-renderer-with-fixtures', cloudIntegration: false, screenshots: 8, baseLibrary: info.SDKVersion }, null, 2));
    console.log('PASS: 8 rendered pages, navigation, local search. Cloud and real-device integration not tested.');
  } finally {
    if (old) await wx('setStorageSync', 'consent-v2', old); else await wx('removeStorageSync', 'consent-v2');
    await wx('reLaunch', { url: '/pages/login/login' }); c.dispose();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
