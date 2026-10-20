'use strict';
const cloud = require('wx-server-sdk');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
const db = cloud.database({ throwOnNotFound: false });
exports.main = async event => {
  const identity = cloud.getWXContext();
  // Scheduled/admin-only: reject all mini-program and Web end-user invocations.
  if (identity.OPENID || identity.FROM_OPENID || identity.UNIONID || identity.UID || identity.APPID || !event || event.Type !== 'Timer') return { ok: false };
  let after = ''; let deleted = 0;
  for (let page = 0; page < 50; page++) {
    const batch = await db.collection('fridge_media').where({ _id: db.command.gt(after) }).orderBy('_id', 'asc').limit(100).get();
    if (!batch.data.length) break;
    for (const record of batch.data) {
      const home = (await db.collection('fridge_homes').doc(record.homeId).get()).data;
      if (home && record.state !== 'deleted' && record.expiresAt > Date.now()) continue;
      if (record.fileID) {
        const result = await cloud.deleteFile({ fileList: [record.fileID] });
        if (result.fileList.some(f => f.status !== 0)) continue;
      }
      await db.runTransaction(async tx => {
        const current = (await tx.collection('fridge_media').doc(record._id).get()).data;
        if (!current) return;
        const family = (await tx.collection('fridge_homes').doc(record.homeId).get()).data;
        if (family && current.state !== 'deleted' && current.expiresAt > Date.now()) return;
        if (family) {
          delete family._id; family.mediaIds = (family.mediaIds || []).filter(id => id !== record._id);
          await tx.collection('fridge_homes').doc(record.homeId).set({ data: family });
        }
        await tx.collection('fridge_media').doc(record._id).remove();
      });
      deleted++;
    }
    after = batch.data[batch.data.length - 1]._id;
  }
  return { ok: true, deleted };
};
