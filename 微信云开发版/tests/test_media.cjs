const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createService, POLICY } = require('../cloudfunctions/fridgeApi/service');
const { createMedia, validFile, sanitizeCandidates } = require('../cloudfunctions/fridgeApi/media');
const parseLabel = require('../miniprogram/utils/label-parser');
class Store {
  constructor() { this.data = new Map(); this.tail = Promise.resolve(); }
  transaction(run) {
    const job = this.tail.then(async () => {
      const draft = structuredClone(this.data);
      const result = await run({
        get: async (c, id) => structuredClone(draft.get(c + '/' + id) || null),
        put: async (c, id, value) => draft.set(c + '/' + id, structuredClone(value)),
        remove: async (c, id) => draft.delete(c + '/' + id)
      });
      this.data = draft; return result;
    });
    this.tail = job.catch(() => {}); return job;
  }
}
async function setup(options = {}) {
  const store = new Store(); let now = Date.now(); let n = 0;
  const service = createService(store, { clock: () => now });
  const identity = who => ({ openid: who, appid: 'app' });
  const request = (who, action, data = {}, key = now + '-' + ++n) => service({ action, data, key }, identity(who));
  for (const who of ['a', 'b']) {
    await request(who, 'login', { policyVersion: POLICY });
    await request(who, 'home.create', { name: who });
  }
  const files = new Map(); let uploads = 0;
  const storage = {
    download: async id => { if (!files.has(id)) throw Error('missing'); return files.get(id); },
    upload: async (path, content) => { uploads++; const id = 'cloud://env.bucket/' + path; files.set(id, content); return id; },
    remove: async ids => ids.forEach(id => files.delete(id)),
    url: async id => 'https://example.invalid/signed/' + id.split('/').pop()
  };
  const media = createMedia({ store, service, storage, enabled: true, env: 'env', clock: () => now, ocr: async () => ({ lines: ['品名：牛奶'] }),
    vision: options.vision === undefined ? async () => ({ candidates: [
      { name: '苹果', quantity: 2, unit: '个', location: '冷藏', expiry: '', confidence: 0.82 },
      { name: '', quantity: 1 },
      { name: '牛奶', quantity: null, unit: '盒', location: '冷冻', expiry: '2026-02-30', confidence: 2 }
    ] }) : options.vision });
  const call = (who, action, data = {}, key = now + '-' + ++n) => media({ action, data, key }, identity(who));
  const image = Buffer.from([255, 216, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 255, 217]);
  async function upload(who) {
    const prepared = await call(who, 'media.prepare', { kind: 'image', size: image.length });
    assert.equal(prepared.ok, true, JSON.stringify(prepared));
    const fileID = 'cloud://env.bucket/' + prepared.data.path; files.set(fileID, image);
    const committed = await call(who, 'media.commit', { id: prepared.data.id, fileID });
    assert.equal(committed.ok, true, JSON.stringify(committed));
    return { ...committed.data, fileID };
  }
  return { store, service, request, call, media, files, identity, upload, image, advance: ms => { now += ms; }, uploads: () => uploads };
}
test('media is gated until private storage is configured', async () => {
  const handler = createMedia({ enabled: false });
  assert.equal((await handler({ action: 'media.prepare' }, {})).error.code, 'MEDIA_SETUP');
});
test('cross-household media access, OCR, deletion and forged upload paths are rejected', async () => {
  const f = await setup(); const photo = await f.upload('a');
  for (const action of ['media.url', 'media.ocr', 'media.recognize', 'media.remove', 'media.commit']) {
    assert.equal((await f.call('b', action, { id: photo.id, fileID: photo.fileID })).ok, false);
  }
  assert.deepEqual((await f.call('b', 'media.list')).data.items, []);
  const slot = (await f.call('a', 'media.prepare', { kind: 'image', size: f.image.length })).data;
  assert.equal((await f.call('a', 'media.commit', { id: slot.id, fileID: photo.fileID })).ok, false);
  assert.equal((await f.call('a', 'media.commit', { id: slot.id, fileID: 'https://evil.invalid/' + slot.path })).ok, false);
});
test('commits survive lost response and shared media cannot be overwritten by source upload', async () => {
  const f = await setup(); const photo = await f.upload('a'); const count = f.uploads();
  assert.equal((await f.call('a', 'media.commit', { id: photo.id, fileID: photo.fileID })).ok, true);
  assert.equal(f.uploads(), count);
  const record = f.store.data.get('fridge_media/' + photo.id);
  assert.match(record.fileID, /\/private-media\//);
  assert.equal(f.files.has(photo.fileID), false);
  assert.equal((await f.call('a', 'media.ocr', { id: photo.id })).ok, true);
  assert.equal((await f.call('a', 'media.ocr', { id: photo.id })).ok, false);
});
test('removed members cannot retrieve family media; expired media cannot be read', async () => {
  const f = await setup(); const photo = await f.upload('a');
  await f.request('b', 'home.leave');
  const home = (await f.request('a', 'session')).data.home;
  await f.request('b', 'home.join', { invite: home.invite });
  assert.equal((await f.call('b', 'media.url', { id: photo.id })).ok, true);
  const b = (await f.request('b', 'session')).data.user;
  await f.request('a', 'home.removeMember', { memberId: b.id });
  assert.equal((await f.call('b', 'media.url', { id: photo.id })).ok, false);
  f.advance(31 * 86400000);
  assert.equal((await f.call('a', 'media.url', { id: photo.id })).ok, false);
});
test('new item only binds a ready unbound photo owned by this user and household', async () => {
  const f = await setup(); const photo = await f.upload('a');
  const item = { name: '奶', quantity: 1, unit: '盒', location: '冷藏', expiry: '', source: 'label', mediaId: photo.id };
  assert.equal((await f.request('b', 'item.add', { items: [item] })).ok, false);
  const added = await f.request('a', 'item.add', { items: [item] });
  assert.equal(added.ok, true);
  assert.equal(f.store.data.get('fridge_media/' + photo.id).itemId, added.data.ids[0]);
  assert.equal((await f.request('a', 'item.add', { items: [item] })).ok, false);
});
test('media format checks reject disguised files and oversize content', () => {
  assert.equal(validFile(Buffer.from('this is not a video file'), 'video'), false);
  assert.equal(validFile(Buffer.alloc(4 * 1024 * 1024 + 1), 'image'), false);
  assert.equal(validFile(Buffer.from('0000ftypisom0000'), 'video'), true);
});
test('OCR parser does not turn production dates or ambiguous labels into expiry', () => {
  const result = parseLabel(['品名：纯牛奶', '生产日期：2026-10-20', '保质期：6个月']);
  assert.equal(result.name, '纯牛奶'); assert.equal(result.production, '2026-10-20');
  assert.equal(result.shelfLife, '6个月'); assert.equal(result.expiry, '');
  assert.equal(parseLabel(['到期日期：2026-02-30']).expiry, '');
  assert.equal(parseLabel(['有效期至：2026/12/20']).expiry, '2026-12-20');
  assert.equal(parseLabel(['到期日期：2026-11-01', '到期日期：2026-12-01']).expiry, '');
});
test('photo recognition returns sanitized suggestions and never writes inventory', async () => {
  const f = await setup(); const photo = await f.upload('a');
  const homeId = (await f.request('a', 'session')).data.home.id;
  const before = f.store.data.get('fridge_homes/' + homeId).items.length;
  const result = await f.call('a', 'media.recognize', { id: photo.id });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.data.candidates.length, 2);
  assert.deepEqual(result.data.candidates[0], { name: '苹果', quantity: 2, unit: '个', location: '冷藏', expiry: '', source: 'manual', confidence: 0.82 });
  assert.deepEqual(result.data.candidates[1], { name: '牛奶', quantity: null, unit: '盒', location: '冷冻', expiry: '', source: 'manual', confidence: null });
  assert.equal(f.store.data.get('fridge_homes/' + homeId).items.length, before);
});
test('recognition is rate limited per photo and needs the service to be configured', async () => {
  const f = await setup(); const photo = await f.upload('a');
  assert.equal((await f.call('a', 'media.recognize', { id: photo.id })).ok, true);
  const blocked = await f.call('a', 'media.recognize', { id: photo.id });
  assert.equal(blocked.ok, false); assert.equal(blocked.error.code, 'INVALID');
  f.advance(61000);
  assert.equal((await f.call('a', 'media.recognize', { id: photo.id })).ok, true);
  const off = await setup({ vision: null }); const other = await off.upload('a');
  const setupError = await off.call('a', 'media.recognize', { id: other.id });
  assert.equal(setupError.ok, false); assert.equal(setupError.error.code, 'VISION_SETUP');
});
test('recognition service failures stay opaque to the client', async () => {
  const f = await setup({ vision: async () => { throw Error('ECONNREFUSED 10.0.0.1'); } });
  const photo = await f.upload('a');
  const result = await f.call('a', 'media.recognize', { id: photo.id });
  assert.equal(result.ok, false); assert.equal(result.error.code, 'VISION_FAILED');
  assert.equal(result.error.message.includes('10.0.0.1'), false);
});
test('recognition output is clamped to the candidate contract', () => {
  assert.deepEqual(sanitizeCandidates([{ name: ' 番茄 ', quantity: 1e9, unit: 'x'.repeat(40), location: '阳台', expiry: '2026-02-30', confidence: -1 }]),
    [{ name: '番茄', quantity: null, unit: 'x'.repeat(12), location: '冷藏', expiry: '', source: 'manual', confidence: null }]);
  assert.throws(() => sanitizeCandidates('nope'), /识别服务返回格式不正确/);
});
