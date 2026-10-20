const api=require('../../utils/api');
Page({media(){wx.navigateTo({url:'/pages/media/media'})},data:{loading:false,busy:false,error:'',home:null,user:null,expiry:''},onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
 async fetch(){const s=await api.call('session');api.session(s);this.setData({home:s.home,user:s.user,expiry:s.home&&s.home.inviteExpires?new Date(s.home.inviteExpires).toLocaleString():''})},
 refresh(){return api.load(this,()=>this.fetch())},
 copy(){wx.setClipboardData({data:this.data.home.invite})},history(){wx.navigateTo({url:'/pages/history/history'})},
 confirm(action,data,title,content,exit=false){wx.showModal({title,content,success:r=>{if(r.confirm)api.run(this,async()=>{await api.write(action,data);if(exit){wx.removeStorageSync('add-draft-v2');wx.reLaunch({url:'/pages/onboarding/onboarding'})}else await this.fetch()})}})},
 rotate(){this.confirm('home.rotate',{},'更换邀请码','旧邀请码将立即失效，新邀请码有效期为 7 天。')},
 remove(e){this.confirm('home.removeMember',{memberId:e.currentTarget.dataset.id},'移除家庭成员','该成员将无法再访问家庭库存，并会更换邀请码。')},
 transfer(e){this.confirm('home.transfer',{memberId:e.currentTarget.dataset.id},'转让家庭管理权','转让后，对方可以管理成员和邀请码，你仍可管理食材。')},
 leave(){this.confirm('home.leave',{},'退出家庭',this.data.home.members.length===1?'你是最后一位成员。退出将删除该家庭的全部库存、采购清单和记录。':'退出后不能继续访问该家庭数据。创建者需先转让管理权。',true)}
});