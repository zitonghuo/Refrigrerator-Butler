const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup(result) {
  let page; let cloudCalls = 0; let options; let preview;
  const wx = {
    stopPullDownRefresh() {},
    requirePrivacyAuthorize: o => o.success(),
    chooseMedia: o => { options = o; result(o); },
    previewImage: o => { preview = o; }
  };
  const api = {
    call() { cloudCalls++; throw Error('Unexpected cloud call'); },
    load() { cloudCalls++; throw Error('Unexpected session load'); },
    async run(p, run) {
      p.setData({ busy: true, error: '' });
      try { await run(); } catch (e) { p.setData({ error: e.message }); }
      finally { p.setData({ busy: false }); }
    }
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../miniprogram/pages/media/media.js'), 'utf8'), {
    wx, Page: p => { page = p; },
    require: p => p.endsWith('/api') ? api : p.endsWith('/config') ? { mediaCloudEnabled: false } : () => ({})
  });
  page.setData = patch => Object.assign(page.data, patch);
  return { page, cloudCalls: () => cloudCalls, options: () => options, preview: () => preview };
}
test('local photo preview and refresh work without session or media cloud requests', async () => {
  const f = setup(o => o.success({ tempFiles: [{ tempFilePath: 'wxfile://photo', size: 100 }] }));
  f.page.onShow();
  await f.page.capture({ currentTarget: { dataset: { kind: 'image' } } });
  assert.equal(f.page.data.local.path, 'wxfile://photo');
  f.page.previewLocal();
  assert.equal(f.preview().current, 'wxfile://photo');
  await f.page.upload(); await f.page.recognize({});
  assert.equal(f.cloudCalls(), 0);
  f.page.clearLocal();
  assert.equal(f.page.data.local, null);
});
test('local video respects duration limits and cancellation preserves existing preview', async () => {
  const f = setup(o => o.success({ tempFiles: [{ tempFilePath: 'wxfile://video', size: 100, duration: 31 }] }));
  await f.page.capture({ currentTarget: { dataset: { kind: 'video' } } });
  assert.equal(f.options().maxDuration, 30);
  assert.equal(f.page.data.local, null);
  assert.match(f.page.data.error, /30 秒/);
  const cancelled = setup(o => o.fail({ errMsg: 'chooseMedia:fail cancel' }));
  cancelled.page.data.local = { path: 'wxfile://previous', kind: 'image' };
  await cancelled.page.capture({ currentTarget: { dataset: { kind: 'image' } } });
  assert.equal(cancelled.page.data.local.path, 'wxfile://previous');
  assert.equal(cancelled.page.data.error, '');
  assert.equal(cancelled.page.data.busy, false);
});
