const api = require('../../utils/api');
const config = require('../../config');
Page({
 data:{busy:false,error:'',accepted:false,name:config.appName,configured:!!config.cloudEnv},
 agreement(e){this.setData({accepted:e.detail.value.includes('agree')})},
 privacy(){wx.navigateTo({url:'/pages/privacy/privacy'})},
 async login(){if(this.data.busy)return;if(!this.data.accepted){this.setData({error:'请先阅读并同意隐私说明。'});return}
  this.setData({busy:true,error:''});
  try{
   const auth=await api.call('login',{policyVersion:config.policyVersion});api.session(auth);wx.setStorageSync('consent-v2',config.policyVersion);
   if(auth.home)wx.switchTab({url:'/pages/home/home'});else wx.reLaunch({url:'/pages/onboarding/onboarding'});
  }catch(error){this.setData({error:error.code==='CONSENT_REQUIRED'?'当前项目与云端版本不一致，请打开共享仓库的 app 目录，更新代码并重新编译后登录。':error.message||'登录未完成，请稍后重试。'})}
  finally{this.setData({busy:false})}}
});
