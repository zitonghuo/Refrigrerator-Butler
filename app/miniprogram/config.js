// Fill cloudEnv after creating a WeChat Cloud Development environment.
module.exports = {
  appName: '小满冰箱',
  appId: 'wx8afbc664265f1bc0',
  cloudEnv: 'cloud1-d1guygnthc98774ff',
  functionName: 'fridgeApi',
  mediaCloudEnabled: false,
  // 开发调试：小程序直连本机 YOLO 服务（仅开发者工具/局域网真机）。
  // 真机测试改成电脑局域网 IP，例如 http://192.168.1.10:8770/recognize；发布前清空。
  // 若本机服务设置了 FRIDGE_VISION_TOKEN，把同一个值填到 visionToken（不要提交真实令牌）。
  visionUrl: 'http://127.0.0.1:8770/recognize',
  visionToken: '',
  policyVersion: '2026-10-20-media',
  operator: '冷鲜栈',
  contactEmail: 'lzy19718010985@outlook.com'
};
