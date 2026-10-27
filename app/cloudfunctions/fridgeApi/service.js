'use strict';
const crypto = require('node:crypto');
const { band, recordStats, summarize, recipeList, todoList } = require('./insights');
const POLICY = '2026-10-20-media';
const COLLECTIONS = { users: 'fridge_users', homes: 'fridge_homes', invites: 'fridge_invites' };
const READS = new Set(['session', 'snapshot', 'item.get', 'report.summary', 'recipe.list', 'todo.list', 'account.export']);
const ACTIONS = new Set([...READS, 'login', 'profile.update', 'home.create', 'home.join', 'home.leave', 'home.rotate', 'home.removeMember', 'home.transfer', 'item.add', 'item.update', 'item.change', 'shopping.add', 'shopping.set', 'shopping.remove', 'account.delete']);
class Fault extends Error { constructor(code, message) { super(message); this.code = code; } }
const check = (ok, code, message) => { if (!ok) throw new Fault(code, message); };
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const random = () => crypto.randomBytes(12).toString('hex');
function text(value, max = 80) { check(typeof value === 'string' && value.trim().length > 0 && value.trim().length <= max, 'INVALID', '文字为空或过长'); return value.trim(); }
function quantity(value, allowZero = false) {
  check(typeof value === 'number' || typeof value === 'string' && value.trim() !== '', 'INVALID', '数量格式不正确');
  const n = Number(value);
  check(Number.isFinite(n) && n >= (allowZero ? 0 : 0.000001) && n <= 1000000 && Math.abs(n * 1e6 - Math.round(n * 1e6)) < 0.001, 'INVALID', '数量需在允许范围内，最多保留六位小数'); return n;
}
function date(value) {
  if (value === '' || value == null) return '';
  check(typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value), 'INVALID', '日期格式不正确');
  const stamp = new Date(value + 'T00:00:00Z');
  check(!Number.isNaN(stamp.getTime()) && stamp.toISOString().slice(0, 10) === value, 'INVALID', '日期不存在'); return value;
}
function fields(data) {
  check(data && typeof data === 'object', 'INVALID', '食材格式不正确');
  check(['冷藏', '冷冻', '常温'].includes(data.location), 'INVALID', '请选择存放位置');
  check(['manual', 'label', 'estimate'].includes(data.source), 'INVALID', '日期来源不正确');
  return { name: text(data.name), unit: text(data.unit, 12), location: data.location, expiry: date(data.expiry), source: data.source };
}
const publicUser = user => ({ id: user.id, name: user.name, homeId: user.homeId, policyVersion: user.policyVersion });const publicHome = (home, uid) => ({ id: home.id, name: home.name, ownerId: home.ownerId, members: home.members, isOwner: home.ownerId === uid, invite: home.ownerId === uid ? home.invite : '', inviteExpires: home.ownerId === uid ? home.inviteExpires : 0 });
function snapshot(home, user, now) {
  return { user: publicUser(user), home: publicHome(home, user.id),
    items: home.items.filter(item => item.quantity > 0).map(item => ({ ...item, band: band(item.expiry, now) })),
    shopping: home.shopping, events: home.events, revision: home.revision };
}
exports.POLICY = POLICY;
exports.createService = (store, options = {}) => {
  const clock = options.clock || Date.now;
  return async (event, identity) => {
    try {
      check(identity && typeof identity.openid === 'string' && identity.openid && typeof identity.appid === 'string' && identity.appid, 'UNAUTHENTICATED', '请通过微信小程序登录');
      check(!options.appId || identity.appid === options.appId, 'FORBIDDEN', '该小程序未获准访问此服务');
      check(event && typeof event === 'object' && !Array.isArray(event) && Buffer.byteLength(JSON.stringify(event)) <= 24000, 'INVALID', '请求内容过大或格式错误');
      const action = event.action; check(ACTIONS.has(action), 'NOT_FOUND', '接口不存在');
      const data = event.data || {}; check(typeof data === 'object' && !Array.isArray(data), 'INVALID', '参数格式错误');
      const uid = hash(identity.appid + ':' + identity.openid);
      const now = clock();
      const isWrite = !READS.has(action) && action !== 'login';
      let key;
      if (isWrite) {
        key = text(event.key, 120);
        const issued = Number(key.split('-')[0]);
        check(Number.isFinite(issued) && issued <= now + 300000 && issued >= now - 24 * 3600000, 'EXPIRED_REQUEST', '操作请求已过期，请刷新并重新操作');
      }
      const result = await store.transaction(async tx => {
        let user = await tx.get(COLLECTIONS.users, uid);
        // A delete whose successful response was lost can safely be repeated.
        if (!user && action === 'account.delete') return { ok: true };
        if (action === 'login') {
          check(data.policyVersion === POLICY, 'CONSENT_REQUIRED', '请阅读并同意当前隐私说明');
          if (!user) user = { id: uid, name: '家庭成员', homeId: '', createdAt: now, receipts: [], rate: { start: now, count: 0 } };
          user.policyVersion = POLICY; user.consentedAt = now;
        }
        check(user, 'UNAUTHENTICATED', '请先登录');
        check(user.policyVersion === POLICY, 'CONSENT_REQUIRED', '请重新阅读并同意隐私说明');
        const rate = user.rate || { start: now, count: 0 };
        user.rate = now - rate.start >= 60000 ? { start: now, count: 1 } : { start: rate.start, count: rate.count + 1 };
        check(user.rate.count <= 100, 'RATE_LIMITED', '操作频繁，请稍后再试');
        user.receipts = (user.receipts || []).filter(r => now - r.time <= 24 * 3600000);
        const fingerprint = isWrite ? hash(JSON.stringify({ action, data })) : '';
        const prior = isWrite && user.receipts.find(r => r.key === key);
        if (prior) {
          check(prior.fingerprint === fingerprint, 'KEY_CONFLICT', '此操作编号已提交不同内容，请核对后再操作');
          await tx.put(COLLECTIONS.users, uid, user);
          return prior.result;
        }
        if (isWrite) check(user.receipts.length < 400, 'DAILY_LIMIT', '今日操作较多，请明天再试');
        let home = user.homeId ? await tx.get(COLLECTIONS.homes, user.homeId) : null;
        if (user.homeId) check(home && home.members.some(m => m.id === uid), 'FORBIDDEN', '家庭权限已变更，请重新登录');
        let output; let homeChanged = false; let deleteUser = false;
        const needHome = () => check(home, 'NO_HOME', '请先创建或加入家庭');
        const owner = () => { needHome(); check(home.ownerId === uid, 'FORBIDDEN', '只有家庭创建者可以执行此操作'); };
        const record = (item, kind, amount) => {
          home.events.unshift({ id: random(), itemId: item.id, name: item.name, kind, quantity: amount, unit: item.unit, actorId: uid, actor: user.name, createdAt: now });
          home.events = home.events.slice(0, 200);
          recordStats(home, item, kind, amount, now);
        };
        const invite = async () => {
          if (home.invite) await tx.remove(COLLECTIONS.invites, hash(home.invite));
          home.invite = crypto.randomBytes(10).toString('hex').toUpperCase(); home.inviteExpires = now + 7 * 86400000;
          await tx.put(COLLECTIONS.invites, hash(home.invite), { homeId: home.id, expiresAt: home.inviteExpires });
        };
        switch (action) {
          case 'login': case 'session': output = { user: publicUser(user), home: home ? publicHome(home, uid) : null }; break;
          case 'snapshot': needHome(); output = snapshot(home, user, now); break;
          case 'report.summary': needHome(); output = summarize(home, data, now); break;
          case 'recipe.list': needHome(); output = recipeList(home, data, now); break;
          case 'todo.list': needHome(); output = todoList(home, now); break;
          case 'account.export': {
            needHome();
            // Data portability: only this user's own household, never the invite code or OpenID.
            output = {
              schemaVersion: '1.0',
              exportedAt: new Date(now).toISOString(),
              user: { id: user.id, name: user.name },
              home: {
                id: home.id, name: home.name, ownerId: home.ownerId,
                members: (home.members || []).map(member => ({ id: member.id, name: member.name }))
              },
              items: home.items || [],
              shopping: home.shopping || [],
              events: home.events || [],
              stats: home.stats || null
            };
            break;
          }
          case 'profile.update':
            user.name = text(data.name, 24);
            if (home) { home.members.find(m => m.id === uid).name = user.name; homeChanged = true; }
            output = { user: publicUser(user) }; break;
          case 'home.create':
            check(!home, 'ALREADY_HOME', '你已经加入家庭，请先退出当前家庭');
            home = { id: random(), name: text(data.name, 30), ownerId: uid, members: [{ id: uid, name: user.name }], items: [], shopping: [], events: [], revision: 0, createdAt: now };
            user.homeId = home.id; await invite(); homeChanged = true; output = { homeId: home.id }; break;
          case 'home.join': {
            check(!home, 'ALREADY_HOME', '请先退出当前家庭');
            const code = text(data.invite, 40).toUpperCase();
            const entry = await tx.get(COLLECTIONS.invites, hash(code));
            check(entry && entry.expiresAt > now, 'INVALID_INVITE', '邀请码无效或已过期');
            home = await tx.get(COLLECTIONS.homes, entry.homeId);
            check(home && home.invite === code && home.inviteExpires > now, 'INVALID_INVITE', '邀请码无效或已过期');
            check(home.members.length < 20, 'LIMIT', '该家庭成员已满 20 人');
            home.members.push({ id: uid, name: user.name }); user.homeId = home.id; homeChanged = true; output = { homeId: home.id }; break;
          }
          case 'home.rotate': owner(); await invite(); homeChanged = true; output = { invite: home.invite, expiresAt: home.inviteExpires }; break;
          case 'home.transfer': {
            owner(); check(data.memberId !== uid && home.members.some(m => m.id === data.memberId), 'INVALID', '请选择其他家庭成员');
            home.ownerId = data.memberId; await invite(); homeChanged = true; output = { ok: true }; break;
          }
          case 'home.removeMember': {
            owner(); check(data.memberId !== uid && home.members.some(m => m.id === data.memberId), 'INVALID', '请选择其他家庭成员');
            const member = await tx.get(COLLECTIONS.users, data.memberId);
            if (member && member.homeId === home.id) { member.homeId = ''; member.receipts = []; await tx.put(COLLECTIONS.users, member.id, member); }
            home.members = home.members.filter(m => m.id !== data.memberId);
            home.events = home.events.map(e => e.actorId === data.memberId ? { ...e, actorId: '', actor: '已离开成员' } : e);
            await invite(); homeChanged = true; output = { ok: true }; break;
          }
          case 'home.leave': case 'account.delete': {
            if (action === 'home.leave') needHome();
            if (home) {
              check(home.ownerId !== uid || home.members.length === 1, 'TRANSFER_REQUIRED', '请先转让家庭管理权，再退出或注销');
              if (home.members.length === 1) {
                await tx.remove(COLLECTIONS.invites, hash(home.invite)); await tx.remove(COLLECTIONS.homes, home.id); home = null;
              } else {
                home.members = home.members.filter(m => m.id !== uid);
                home.events = home.events.map(e => e.actorId === uid ? { ...e, actorId: '', actor: action === 'account.delete' ? '已注销成员' : '已离开成员' } : e);
                homeChanged = true;
              }
            }
            user.homeId = ''; user.receipts = [];
            if (action === 'account.delete') { await tx.remove(COLLECTIONS.users, uid); deleteUser = true; }
            output = { ok: true }; break;
          }
          case 'item.get': {
            needHome(); const item = home.items.find(i => i.id === data.id);
            check(item, 'NOT_FOUND', '食材不存在或已移除'); output = { item: { ...item, band: band(item.expiry, now) }, events: home.events.filter(e => e.itemId === item.id) }; break;
          }
          case 'item.add': {
            needHome(); check(Array.isArray(data.items) && data.items.length >= 1 && data.items.length <= 20, 'INVALID', '每次可添加 1 至 20 项食材');
            check(home.items.length + data.items.length <= 300, 'LIMIT', '最多保存 300 批在库食材，请先整理库存');
            const ids = [];
            for (const input of data.items) {
              const item = { ...fields(input), quantity: quantity(input.quantity), id: random(), version: 1, createdAt: now };
              if (input.mediaId) {
                const media = await tx.get('fridge_media', input.mediaId);
                check(media && media.homeId === home.id && media.ownerId === uid && media.state === 'ready' && media.expiresAt > now && !media.itemId, 'INVALID', '照片已失效或已关联食材，请重新选择');
                media.itemId = item.id; await tx.put('fridge_media', media.id, media);
              }
              home.items.push(item); record(item, '入库', item.quantity); ids.push(item.id);
            }
            homeChanged = true; output = { ids }; break;
          }
          case 'item.update': case 'item.change': {
            needHome(); const item = home.items.find(i => i.id === data.id); check(item, 'NOT_FOUND', '食材不存在或已消耗完');
            check(Number.isInteger(data.version) && item.version === data.version, 'CONFLICT', '库存已更新，请刷新后再操作');
            if (action === 'item.update') { Object.assign(item, fields(data)); record(item, '修改资料', 0); }
            else {
              check(['消耗', '丢弃', '盘点'].includes(data.kind), 'INVALID', '操作不正确');
              const n = quantity(data.quantity, data.kind === '盘点');
              check(data.kind === '盘点' || n <= item.quantity, 'INVALID', '数量超过当前库存');
              const next = data.kind === '盘点' ? n : Math.round((item.quantity - n) * 1e6) / 1e6;
              record(item, data.kind, data.kind === '盘点' ? next - item.quantity : n); item.quantity = next;
            }
            item.version++; home.items = home.items.filter(i => i.quantity > 0); homeChanged = true; output = { ok: true }; break;
          }
          case 'shopping.add':
            needHome(); check(home.shopping.length < 100, 'LIMIT', '采购清单已满，请先删除不再需要的项目');
            home.shopping.unshift({ id: random(), name: text(data.name), done: false, version: 1, createdAt: now }); homeChanged = true; output = { ok: true }; break;
          case 'shopping.set': case 'shopping.remove': {
            needHome(); const item = home.shopping.find(i => i.id === data.id); check(item, 'NOT_FOUND', '采购项已移除');
            check(item.version === data.version, 'CONFLICT', '采购清单已更新，请刷新');
            if (action === 'shopping.remove') home.shopping = home.shopping.filter(i => i.id !== item.id);
            else { check(typeof data.done === 'boolean', 'INVALID', '采购状态不正确'); item.done = data.done; item.version++; }
            homeChanged = true; output = { ok: true }; break;
          }
        }
        if (homeChanged && home) {
          home.revision++;
          check(Buffer.byteLength(JSON.stringify(home)) < 700000, 'LIMIT', '家庭数据过多，请先整理');
          await tx.put(COLLECTIONS.homes, home.id, home);
        }
        if (!deleteUser) {
          if (isWrite) user.receipts.push({ key, fingerprint, result: output, time: now });
          await tx.put(COLLECTIONS.users, uid, user);
        }
        return output;
      });
      return { ok: true, data: result };
    } catch (error) {
      if (error instanceof Fault) return { ok: false, error: { code: error.code, message: error.message } };
      // Do not log event, OPENID, invitations or household content.
      console.error('fridge-api failure', error.code || 'INTERNAL');
      return { ok: false, error: { code: 'INTERNAL', message: '服务暂时不可用，请稍后重试；未确认的操作请使用原请求重试' } };
    }
  };
};
