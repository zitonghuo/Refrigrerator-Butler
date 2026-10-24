const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function load(config, wx) {
  const sandbox = { module: { exports: {} }, exports: {}, require: p => p.endsWith('config') ? config : {}, wx };
  vm.runInNewContext(fs.readFileSync(require.resolve('../miniprogram/utils/vision.js'), 'utf8'), sandbox);
  return sandbox.module.exports;
}

function wxWith({ statusCode = 200, body, requestFails = false, readFails = false, capture } = {}) {
  return {
    getFileSystemManager: () => ({
      readFile: options => readFails ? options.fail({ errMsg: 'read:fail' }) : options.success({ data: 'BASE64DATA' })
    }),
    request: options => {
      if (capture) capture(options);
      if (requestFails) options.fail({ errMsg: 'request:fail' });
      else options.success({ statusCode, data: body });
    }
  };
}

test('sends the photo as base64 JSON and normalizes candidates', async () => {
  let captured;
  const vision = load(
    { visionUrl: 'http://127.0.0.1:8770/recognize', visionToken: '' },
    wxWith({
      body: { candidates: [{ name: ' 西瓜 ', quantity: 1, unit: '个', location: '冷藏', expiry: '', confidence: 0.92345 }] },
      capture: options => { captured = options; }
    })
  );
  const list = await vision.recognize('wxfile://photo.jpg');
  assert.equal(captured.method, 'POST');
  assert.equal(captured.url, 'http://127.0.0.1:8770/recognize');
  assert.equal(captured.data.kind, 'photo');
  assert.equal(captured.data.images[0], 'BASE64DATA');
  assert.equal(captured.header.Authorization, undefined);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(list[0])), { name: '西瓜', quantity: 1, unit: '个', location: '冷藏', expiry: '', source: 'manual', confidence: 0.9235 });
});

test('adds the bearer token only when one is configured', async () => {
  let captured;
  const vision = load(
    { visionUrl: 'http://127.0.0.1:8770/recognize', visionToken: 'dev-token' },
    wxWith({ body: { candidates: [] }, capture: options => { captured = options; } })
  );
  await vision.recognize('wxfile://photo.jpg');
  assert.equal(captured.header.Authorization, 'Bearer dev-token');
});

test('surfaces service errors and connection failures', async () => {
  const unavailable = load({ visionUrl: 'http://127.0.0.1:8770/recognize' }, wxWith({ statusCode: 503, body: { error: '模型未就绪' } }));
  await assert.rejects(unavailable.recognize('a'), /模型未就绪/);

  const offline = load({ visionUrl: 'http://127.0.0.1:8770/recognize' }, wxWith({ requestFails: true }));
  await assert.rejects(offline.recognize('a'), /连不上本机识别服务/);

  const unreadable = load({ visionUrl: 'http://127.0.0.1:8770/recognize' }, wxWith({ readFails: true }));
  await assert.rejects(unreadable.recognize('a'), /读取图片失败/);

  const malformed = load({ visionUrl: 'http://127.0.0.1:8770/recognize' }, wxWith({ body: { lines: [] } }));
  await assert.rejects(malformed.recognize('a'), /格式不正确/);
});

test('candidate fields are clamped to the app contract', () => {
  const vision = load({ visionUrl: 'http://x/recognize' }, wxWith());
  const list = vision.normalize([
    { name: '   ' },
    { name: '番茄', quantity: 1e9, unit: 'x'.repeat(20), location: '阳台', expiry: '2026-02-30', confidence: 2 },
    { name: '鸡蛋', quantity: '3', unit: '个', location: '冷藏', expiry: '2026-10-30', confidence: -1 }
  ]);
  assert.equal(list.length, 2);
  const plain = JSON.parse(JSON.stringify(list));
  assert.deepStrictEqual(plain[0], { name: '番茄', quantity: null, unit: 'x'.repeat(12), location: '冷藏', expiry: '', source: 'manual', confidence: null });
  assert.deepStrictEqual(plain[1], { name: '鸡蛋', quantity: null, unit: '个', location: '冷藏', expiry: '2026-10-30', source: 'label', confidence: null });
});

test('disabled when no visionUrl is configured', async () => {
  const vision = load({ visionUrl: '' }, wxWith());
  assert.equal(vision.enabled(), false);
  await assert.rejects(vision.recognize('a'), /未配置/);
});
