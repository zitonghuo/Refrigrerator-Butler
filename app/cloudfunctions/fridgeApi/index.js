'use strict';
const cloud = require('wx-server-sdk');
const { createService } = require('./service');
const { createStore } = require('./store');
const { createMedia } = require('./media');
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });
// A first-time user / invalid invite is a normal missing-document result.
// SDK 4 defaults to throwing for missing documents, so opt out explicitly.
const store = createStore(cloud.database({ throwOnNotFound: false }));
const service = createService(store, {
  appId: process.env.EXPECTED_APPID || 'wx8afbc664265f1bc0'
});
const media = createMedia({
  store, service, env: process.env.TCB_ENV || process.env.SCF_NAMESPACE,
  enabled: process.env.MEDIA_READY === 'true',
  storage: {
    download: async fileID => (await cloud.downloadFile({ fileID })).fileContent,
    upload: async (cloudPath, fileContent) => (await cloud.uploadFile({ cloudPath, fileContent })).fileID,
    remove: fileList => cloud.deleteFile({ fileList }),
    url: async fileID => {
      const result = await cloud.getTempFileURL({ fileList: [{ fileID, maxAge: 60 }] });
      const file = result.fileList[0];
      if (!file || file.status !== 0 || !file.tempFileURL) throw Error('URL_FAILED');
      return file.tempFileURL;
    }
  },
  ocr: process.env.OCR_URL && process.env.OCR_TOKEN ? async image => {
    const url = new URL(process.env.OCR_URL);
    if (url.protocol !== 'https:') throw Error('OCR_HTTPS_REQUIRED');
    const response = await fetch(url, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(45000),
      headers: { 'Content-Type': 'application/octet-stream', Authorization: 'Bearer ' + process.env.OCR_TOKEN },
      body: image
    });
    if (!response.ok) throw Error('OCR_UNAVAILABLE');
    const body = await response.text();
    if (body.length > 32000) throw Error('OCR_RESPONSE_LIMIT');
    const value = JSON.parse(body);
    if (!Array.isArray(value.lines)) throw Error('OCR_RESPONSE_INVALID');
    return { lines: value.lines.filter(x => typeof x === 'string').slice(0, 80).map(x => x.slice(0, 200)) };
  } : null,
  // Optional food detector (YOLOv8 service). Keep it server-side: the token never reaches the client.
  vision: process.env.VISION_URL && process.env.VISION_TOKEN ? async image => {
    const url = new URL(process.env.VISION_URL);
    if (url.protocol !== 'https:') throw Error('VISION_HTTPS_REQUIRED');
    const response = await fetch(url, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(45000),
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + process.env.VISION_TOKEN },
      body: JSON.stringify({ kind: 'photo', images: [image.toString('base64')] })
    });
    if (!response.ok) throw Error('VISION_UNAVAILABLE');
    const body = await response.text();
    if (body.length > 32000) throw Error('VISION_RESPONSE_LIMIT');
    const value = JSON.parse(body);
    if (!Array.isArray(value.candidates)) throw Error('VISION_RESPONSE_INVALID');
    return { candidates: value.candidates };
  } : null
});
exports.main = async event => {
  const context = cloud.getWXContext();
  const identity = { openid: context.OPENID, appid: context.APPID };
  if (event && typeof event.action === 'string' && event.action.startsWith('media.')) return media(event, identity);
  return service(event, identity);
};
