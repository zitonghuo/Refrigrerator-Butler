const config = require('../config');
const labels = { expired: '已过期', urgent: '今天到期', soon: '3 天内', week: '7 天内', fresh: '7 天以上', unknown: '日期待补' };
function fail(code, message) { const error = new Error(message); error.code = code; return error; }
async function call(action, data = {}, key) {
  if (!config.cloudEnv) throw fail('NOT_CONFIGURED', '云服务尚未部署，请开发者先配置云环境。');
  let response;
  try { response = await wx.cloud.callFunction({ name: config.functionName, data: { action, data, ...(key ? { key } : {}) }, config: { env: config.cloudEnv } }); }
  catch (error) { throw fail('NETWORK', '连接未完成，请检查网络后重试。已提交的操作会按原请求核对。'); }
  const result = response.result;
  if (!result || !result.ok) throw fail(result && result.error ? result.error.code : 'INTERNAL', result && result.error ? result.error.message : '服务返回异常');
  return result.data;
}
function session(value) {
  getApp().globalData.session = value;
  if (value && value.user) wx.setStorageSync('last-user-v2', value.user.id);
}
function current() { return getApp().globalData.session; }
// Persist the exact request before sending. Retrying after timeout/app restart
// reuses the same key and payload instead of creating a second inventory batch.
async function write(action, data) {
  const auth = current();
  if (!auth || !auth.user) throw fail('UNAUTHENTICATED', '请先登录');
  const storageKey = 'pending-v2-' + auth.user.id;
  let pending = wx.getStorageSync(storageKey);
  if (pending) {
    if (pending.action !== action || JSON.stringify(pending.data) !== JSON.stringify(data)) throw fail('PENDING', '还有一笔操作未确认，请到个人中心恢复提交后再继续。');
  } else {
    pending = { action, data, key: Date.now() + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2) };
    wx.setStorageSync(storageKey, pending);
  }
  try {
    const result = await call(pending.action, pending.data, pending.key);
    wx.removeStorageSync(storageKey); return result;
  } catch (error) {
    if (!['NETWORK', 'INTERNAL'].includes(error.code)) wx.removeStorageSync(storageKey);
    throw error;
  }
}
async function resume() {
  const auth = current(); const pending = auth && wx.getStorageSync('pending-v2-' + auth.user.id);
  if (!pending) return false;
  await write(pending.action, pending.data); return pending.action;
}
function hasPending() { const auth = current(); return !!(auth && wx.getStorageSync('pending-v2-' + auth.user.id)); }
function clearLocal() {
  const auth = current();
  const uid = auth ? auth.user.id : wx.getStorageSync('last-user-v2');
  if (uid) wx.removeStorageSync('pending-v2-' + uid);
  wx.removeStorageSync('last-user-v2');
  wx.removeStorageSync('consent-v2');
  wx.removeStorageSync('add-draft-v2');
  session(null);
}
async function ensure(home = true) {
  if (wx.getStorageSync('consent-v2') !== config.policyVersion) { wx.reLaunch({ url: '/pages/login/login' }); return false; }
  let value;
  try { value = await call('session'); }
  catch (error) {
    const uid = wx.getStorageSync('last-user-v2');
    const pending = uid && wx.getStorageSync('pending-v2-' + uid);
    if (error.code === 'UNAUTHENTICATED' && pending && pending.action === 'account.delete') {
      clearLocal(); wx.reLaunch({ url: '/pages/login/login' }); return false;
    }
    throw error;
  }
  session(value);
  if (home && !value.home) { wx.reLaunch({ url: '/pages/onboarding/onboarding' }); return false; }
  return value;
}
function decorate(item) { return { ...item, label: labels[item.band] || '日期待补' }; }
function message(page, error) {
  if (['UNAUTHENTICATED', 'CONSENT_REQUIRED'].includes(error.code)) { session(null); wx.reLaunch({ url: '/pages/login/login' }); }
  else if (error.code === 'NO_HOME') wx.reLaunch({ url: '/pages/onboarding/onboarding' });
  else page.setData({ error: error.message });
}
async function load(page, callback, home = true) {
  if (page.data.loading || page.data.busy) return;
  page.setData({ loading: true, error: '' });
  try { const auth = await ensure(home); if (auth) await callback(auth); }
  catch (error) { message(page, error); }
  finally { page.setData({ loading: false }); wx.stopPullDownRefresh(); }
}
async function run(page, callback) {
  if (page.data.busy || page.data.loading) return;
  page.setData({ busy: true, error: '' });
  try { await callback(); }
  catch (error) { message(page, error); }
  finally { page.setData({ busy: false }); }
}
module.exports = { call, write, resume, hasPending, session, current, clearLocal, ensure, decorate, message, load, run };
