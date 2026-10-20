'use strict';
const crypto = require('node:crypto');
const hash = s => crypto.createHash('sha256').update(s).digest('hex');
const fault = (code, message) => Object.assign(new Error(message), { code, public: true });
const demand = (ok, message) => { if (!ok) throw fault('INVALID', message); };
const LIMITS = { image: 4 * 1024 * 1024, video: 12 * 1024 * 1024 };
function validFile(buffer, kind) {
  if (!Buffer.isBuffer(buffer) || buffer.length > LIMITS[kind] || buffer.length < 12) return false;
  if (kind === 'video') return buffer.toString('ascii', 4, 8) === 'ftyp';
  return buffer.subarray(0, 3).equals(Buffer.from([255, 216, 255])) ||
    buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
}
exports.validFile = validFile;
exports.createMedia = ({ store, service, storage, env, enabled, ocr, clock = Date.now }) => async (event, identity) => {
  try {
    if (!enabled) throw fault('MEDIA_SETUP', '照片和视频云服务正在配置，请稍后使用；手动入库不受影响。');
    const auth = await service({ action: 'session' }, identity);
    if (!auth.ok) return auth;
    const user = auth.data.user;
    if (!auth.data.home) throw fault('NO_HOME', '请先创建或加入家庭');
    const data = event.data || {};
    const now = clock();
    // Every transaction rechecks membership; never trust a client homeId or file path.
    async function transaction(run) {
      return store.transaction(async tx => {
        const current = await tx.get('fridge_users', user.id);
        const home = current && current.homeId && await tx.get('fridge_homes', current.homeId);
        if (!home || !home.members.some(m => m.id === user.id)) throw fault('FORBIDDEN', '家庭权限已变更');
        return run(tx, home);
      });
    }
    async function find(tx, home) {
      demand(typeof data.id === 'string' && /^[a-f0-9]{64}$/.test(data.id), '附件编号无效');
      const record = await tx.get('fridge_media', data.id);
      if (!record || record.homeId !== home.id || record.expiresAt <= now || record.state === 'deleted') throw fault('NOT_FOUND', '附件不存在或已过期');
      return record;
    }
    const publicRecord = r => ({ id: r.id, kind: r.kind, itemId: r.itemId, expiresAt: r.expiresAt, size: r.size });
    let output;
    if (event.action === 'media.prepare') {
      demand(Object.hasOwn(LIMITS, data.kind), '请选择照片或视频');
      demand(Number.isInteger(data.size) && data.size > 0 && data.size <= LIMITS[data.kind], '照片最多 4 MB，视频最多 12 MB');
      const key = event.key;
      demand(typeof key === 'string' && key.length <= 120 && Number(key.split('-')[0]) >= now - 86400000 && Number(key.split('-')[0]) <= now + 300000, '上传请求已过期');
      const id = hash(user.id + ':' + key);
      output = await transaction(async (tx, home) => {
        const previous = await tx.get('fridge_media', id);
        if (previous) {
          demand(previous.homeId === home.id && previous.ownerId === user.id && previous.state === 'pending' && previous.expiresAt > now &&
            previous.kind === data.kind && previous.size === data.size && previous.itemId === (data.itemId || ''), '上传请求已变更，请重新选择文件');
          return { id, path: previous.path };
        }
        if (data.itemId) demand(home.items.some(i => i.id === data.itemId), '食材已移除');
        const ids = home.mediaIds || [];
        demand(ids.length < 100, '家庭最多保留 100 个附件，请先删除不再需要的附件');
        const path = 'staging/' + identity.openid + '/' + id;
        await tx.put('fridge_media', id, { id, path, ownerId: user.id, homeId: home.id, itemId: data.itemId || '', kind: data.kind, size: data.size, state: 'pending', createdAt: now, expiresAt: now + 86400000 });
        home.mediaIds = [...ids, id]; await tx.put('fridge_homes', home.id, home);
        return { id, path };
      });
    } else if (event.action === 'media.commit') {
      const record = await transaction(async (tx, home) => {
        const r = await find(tx, home); demand(r.ownerId === user.id, '只能完成自己的上传'); return r;
      });
      if (record.state === 'ready') output = publicRecord(record);
      else {
        demand(typeof data.fileID === 'string' && data.fileID.startsWith('cloud://' + env + '.') && data.fileID.endsWith('/' + record.path), '上传文件不属于当前请求');
        const content = await storage.download(data.fileID);
        demand(content.length === record.size && validFile(content, record.kind), '文件大小或格式不符合要求，请使用 JPG、PNG 或 MP4 视频');
        // Copy to a server-only path: uploader cannot overwrite shared media later.
        const fileID = await storage.upload('private-media/' + record.homeId + '/' + record.id, content);
        try {
          output = await transaction(async (tx, home) => {
            const current = await find(tx, home);
            demand(current.ownerId === user.id, '上传身份已变更');
            if (current.state === 'ready') return publicRecord(current);
            demand(current.state === 'pending', '上传已取消');
            Object.assign(current, { fileID, state: 'ready', expiresAt: now + 30 * 86400000 });
            await tx.put('fridge_media', current.id, current); return publicRecord(current);
          });
        } catch (error) { /* The storage lifecycle removes unreferenced server copies. */ throw error; }
        await storage.remove([data.fileID]).catch(() => {});
      }
    } else if (event.action === 'media.list') {
      output = await transaction(async (tx, home) => {
        const list = [];
        for (const id of home.mediaIds || []) {
          const r = await tx.get('fridge_media', id);
          if (r && r.state === 'ready' && r.expiresAt > now && (!data.itemId || r.itemId === data.itemId)) list.push(publicRecord(r));
        }
        return { items: list };
      });
    } else if (['media.url', 'media.ocr', 'media.remove'].includes(event.action)) {
      const record = await transaction(async (tx, home) => {
        const r = await find(tx, home);
        if (event.action !== 'media.remove') demand(r.state === 'ready', '附件尚未完成上传');
        if (event.action === 'media.remove') {
          r.state = 'deleted'; await tx.put('fridge_media', r.id, r);
          home.mediaIds = (home.mediaIds || []).filter(id => id !== r.id);
          await tx.put('fridge_homes', home.id, home);
        }
        return r;
      });
      if (event.action === 'media.remove') {
        if (record.fileID) await storage.remove([record.fileID]).catch(() => {});
        output = { ok: true };
      } else if (event.action === 'media.url') output = { url: await storage.url(record.fileID), expiresIn: 60 };
      else {
        demand(record.kind === 'image', '请选择包装照片进行识别');
        if (!ocr) throw fault('OCR_SETUP', '包装识别服务尚未部署，照片已保存，可以先手动填写。');
        // Limit expensive inference independently of the ordinary API rate limit.
        await transaction(async (tx, home) => {
          const r = await find(tx, home);
          demand(!r.lastOcrAt || now - r.lastOcrAt >= 60000, '请间隔一分钟再识别这张照片');
          r.lastOcrAt = now; await tx.put('fridge_media', r.id, r);
        });
        output = await ocr(await storage.download(record.fileID));
        await transaction((tx, home) => find(tx, home)); // Recheck after slow inference.
      }
    } else throw fault('NOT_FOUND', '附件接口不存在');
    return { ok: true, data: output };
  } catch (error) {
    return { ok: false, error: { code: error.public ? error.code : 'MEDIA_FAILED', message: error.public ? error.message : '附件处理未完成，请刷新附件列表核对后重试。' } };
  }
};
