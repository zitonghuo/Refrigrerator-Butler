const api = require('./api');

// Budget for the encoded field as sent over the wire, including Base64 expansion.
const maxEncodedLength = 80 * 1024;
const presets = [[1280, 82], [1024, 74], [896, 64], [768, 55], [640, 50], [512, 42], [384, 30]];

async function recognize(path, consentVersion, kind = 'photo') {
  async function send(imageBase64) {
    const response = await api.call('vision.recognize', { imageBase64, consentVersion, kind:kind === 'receipt' ? 'receipt-lines' : kind });
    if (kind === 'single' && response.kind !== 'single') throw Error('请先部署新版 fridgeApi 云函数，以启用单品识别。');
    return kind === 'receipt' ? require('./receipt-ocr').receiptRows(response.lines) : response.candidates;
  }
  if (kind === 'receipt') {
    const fs = wx.getFileSystemManager();
    const info = await new Promise((success, fail) => fs.stat({ path, success, fail }));
    if (info.stats.size <= maxEncodedLength * 3 / 4) {
      const file = await new Promise((success, fail) => fs.readFile({ filePath: path, encoding: 'base64', success, fail }));
      if (/^(?:iVBORw0KGgo|\/9j\/)/.test(file.data)) {
        return send(file.data);
      }
    }
  }
  for (const [compressedWidth, quality] of presets) {
    const image = await new Promise((success, fail) => {
      wx.compressImage({ src: path, compressedWidth, quality, success, fail });
    });
    const file = await new Promise((success, fail) => {
      wx.getFileSystemManager().readFile({
        filePath: image.tempFilePath, encoding: 'base64', success, fail
      });
    });
    if (file.data.length > maxEncodedLength) continue;
    return send(file.data);
  }
  throw Error('这张照片压缩后仍然太大，请裁剪到食材所在区域再试。');
}

module.exports = { recognize };
