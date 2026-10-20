const api = require('../../utils/api');
const config = require('../../config');
Page({
 data:{busy:false,error:'',accepted:false,name:config.appName,configured:!!config.cloudEnv},
 agreement(e){this.setData({accepted:e.detail.value.includes('agree')})},
 privacy(){wx.navigateTo({url:'/pages/privacy/privacy'})},
 login(){if(!this.data.accepted){this.setData({error:'请先阅读并同意隐私说明。'});return}
  return api.run(this,async()=>{
   const auth=await api.call('login',{policyVersion:config.policyVersion});api.session(auth);wx.setStorageSync('consent-v2',config.policyVersion);
   if(auth.home)wx.switchTab({url:'/pages/home/home'});else wx.reLaunch({url:'/pages/onboarding/onboarding'});
  })}
});