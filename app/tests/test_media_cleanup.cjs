const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture(identity = {}, failDelete = false) {
  const now = Date.now();
  const records = new Map([
    ['expired', { _id: 'expired', homeId: 'home', state: 'ready', expiresAt: now - 1, fileID: 'expired-file' }],
    ['live', { _id: 'live', homeId: 'home', state: 'ready', expiresAt: now + 86400000, fileID: 'live-file' }],
    ['orphan', { _id: 'orphan', homeId: 'gone', state: 'ready', expiresAt: now + 86400000, fileID: 'orphan-file' }]
  ]);
  const homes = new Map([['home', { _id: 'home', mediaIds: ['expired', 'live'] }]]);
  const removedFiles = [];
  let queries = 0;
  const db = {
    command: { gt: value => value },
    collection(name) {
      const data = name === 'fridge_media' ? records : homes;
      return {
        where({ _id: after }) {
          queries++;
          return { orderBy: () => ({ limit: () => ({ get: async () => ({
            data: [...data.values()].filter(r => r._id > after).sort((a, b) => a._id.localeCompare(b._id))
          }) }) }) };
        },
        doc(id) {
          return {
            get: async () => ({ data: data.has(id) ? structuredClone(data.get(id)) : null }),
            set: async ({ data: value }) => data.set(id, { ...structuredClone(value), _id: id }),
            remove: async () => data.delete(id)
          };
        }
      };
    },
    runTransaction: async run => run(db)
  };
  const cloud = {
    init() {}, getWXContext: () => identity, database: () => db,
    deleteFile: async ({ fileList }) => {
      if (!failDelete) removedFiles.push(...fileList);
      return { fileList: fileList.map(() => ({ status: failDelete ? -1 : 0 })) };
    }
  };
  const sandbox = { exports: {}, require: name => {
    assert.equal(name, 'wx-server-sdk'); return cloud;
  } };
  vm.runInNewContext(fs.readFileSync(require.resolve('../cloudfunctions/fridgeMediaCleanup/index.js'), 'utf8'), sandbox);
  return { run: sandbox.exports.main, records, homes, removedFiles, queries: () => queries };
}

test('cleanup rejects end-user calls even when the caller forges a timer event', async () => {
  for (const field of ['OPENID', 'FROM_OPENID', 'UNIONID', 'UID', 'APPID']) {
    const f = fixture({ [field]: 'user' });
    assert.equal((await f.run({ Type: 'Timer' })).ok, false);
    assert.equal(f.queries(), 0);
  }
  const f = fixture();
  assert.equal((await f.run({})).ok, false);
  assert.equal(f.queries(), 0);
});
test('cleanup removes expired and orphaned files while preserving current family media', async () => {
  const f = fixture();
  assert.equal((await f.run({ Type: 'Timer' })).deleted, 2);
  assert.deepEqual([...f.records.keys()], ['live']);
  assert.deepEqual(f.homes.get('home').mediaIds, ['live']);
  assert.deepEqual(f.removedFiles, ['expired-file', 'orphan-file']);
});
test('failed physical deletion retains metadata and quota references for a later retry', async () => {
  const f = fixture({}, true);
  assert.equal((await f.run({ Type: 'Timer' })).deleted, 0);
  assert.equal(f.records.size, 3);
  assert.deepEqual(f.homes.get('home').mediaIds, ['expired', 'live']);
});
