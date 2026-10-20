const config = require('./config');
App({
  globalData: { session: null },
  onLaunch() {
    if (wx.cloud && config.cloudEnv) wx.cloud.init({ env: config.cloudEnv, traceUser: false });
  }
});
