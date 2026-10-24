// Development-only bridge to the local YOLO service (vision/).
// The photo is sent as base64 JSON directly from the mini program, so it does not
// touch cloud storage and works on the free tier. Not for production use.
const config = require('../config');

const LOCATIONS = ['冷藏', '冷冻', '常温'];
const LIMIT = 20;

const readBase64 = filePath => new Promise((resolve, reject) => {  wx.getFileSystemManager().readFile({
    filePath,
    encoding: 'base64',
    success: result => resolve(result.data),
    fail: () => reject(new Error('读取图片失败，请重新选择'))
  });
});

const post = options => new Promise((resolve, reject) => {
  wx.request({ ...options, success: resolve, fail: reject });
});

function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
  const stamp = new Date(value + 'T00:00:00Z');
  return !Number.isNaN(stamp.getTime()) && stamp.toISOString().slice(0, 10) === value ? value : '';
}

function normalize(list) {
  const out = [];
  for (const raw of (Array.isArray(list) ? list : []).slice(0, LIMIT)) {
    if (!raw || typeof raw !== 'object' || typeof raw.name !== 'string') continue;
    const name = raw.name.trim().slice(0, 80);
    if (!name) continue;
    const quantity = typeof raw.quantity === 'number' && Number.isFinite(raw.quantity) && raw.quantity > 0 && raw.quantity <= 1000000
      ? Math.round(raw.quantity * 1e6) / 1e6 : null;
    const unit = typeof raw.unit === 'string' && raw.unit.trim() ? raw.unit.trim().slice(0, 12) : '个';
    const location = LOCATIONS.includes(raw.location) ? raw.location : '冷藏';
    const expiry = validDate(raw.expiry);
    const confidence = typeof raw.confidence === 'number' && Number.isFinite(raw.confidence) && raw.confidence >= 0 && raw.confidence <= 1
      ? Math.round(raw.confidence * 10000) / 10000 : null;
    out.push({ name, quantity, unit, location, expiry, source: expiry ? 'label' : 'manual', confidence });
  }
  return out;
}

async function recognize(filePath) {
  if (!config.visionUrl) throw new Error('本机识别服务未配置，请在 config.js 设置 visionUrl');
  const data = await readBase64(filePath);
  let response;
  try {
    response = await post({
      url: config.visionUrl,
      method: 'POST',
      header: {
        'content-type': 'application/json',
        ...(config.visionToken ? { Authorization: 'Bearer ' + config.visionToken } : {})
      },
      data: { kind: 'photo', images: [data] },
      timeout: 60000
    });
  } catch (error) {
    throw new Error('连不上本机识别服务：请确认 vision 服务已启动，且手机与电脑在同一局域网');
  }
  const body = response && response.data;
  if (!response || response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error((body && body.error) || '识别服务返回异常，请稍后重试');
  }
  if (!body || !Array.isArray(body.candidates)) throw new Error('识别服务返回格式不正确');
  return normalize(body.candidates);
}

module.exports = { recognize, normalize, enabled: () => Boolean(config.visionUrl) };
