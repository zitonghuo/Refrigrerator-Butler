const api=require('../../utils/api');
const config=require('../../config');
Page({data:{loading:false,busy:false,error:'',user:null,name:'',home:null,pending:false,email:config.contactEmail},onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
 refresh(){return api.load(this,async s=>{this.setData({user:s.user,name:s.user.name,home:s.home,pending:api.hasPending()})},false)},input(e){this.setData({name:e.detail.value})},
 save(){return api.run(this,async()=>{await api.write('profile.update',{name:this.data.name.trim()});const s=await api.call('session');api.session(s);this.setData({user:s.user});wx.showToast({title:'已保存'})})},
 recover(){return api.run(this,async()=>{const action=await api.resume();this.setData({pending:api.hasPending()});if(action==='account.delete'){api.clearLocal();wx.reLaunch({url:'/pages/login/login'})}else {await api.ensure(false);wx.showToast({title:'已核对提交'});if(action==='home.leave')wx.reLaunch({url:'/pages/onboarding/onboarding'})}})},
 privacy(){wx.navigateTo({url:'/pages/privacy/privacy'})},contact(){wx.setClipboardData({data:config.contactEmail})},
 home(){wx.reLaunch({url:'/pages/onboarding/onboarding'})},
 logout(){if(api.hasPending()){this.setData({error:'请先恢复未确认的提交，避免丢失操作状态。'});return}wx.showModal({title:'退出登录',content:'退出会清除本机草稿；云端家庭数据保留，下次可用同一微信登录。',success:r=>{if(r.confirm){api.clearLocal();wx.reLaunch({url:'/pages/login/login'})}}})},
 remove(){wx.showModal({title:'注销账号',content:'删除账号与本机草稿；共享操作记录将匿名化。若你是最后一位家庭成员，家庭数据也会删除。不可撤销。',confirmText:'确认注销',confirmColor:'#a33542',success:r=>{if(r.confirm)api.run(this,async()=>{await api.write('account.delete',{});api.clearLocal();wx.reLaunch({url:'/pages/login/login'})})}})}
});