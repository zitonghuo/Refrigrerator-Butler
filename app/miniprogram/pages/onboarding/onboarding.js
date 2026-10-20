const api=require('../../utils/api');
Page({data:{loading:false,busy:false,error:'',mode:'create',name:'我们的小厨房',invite:''},
 onShow(){api.load(this,async auth=>{if(auth.home)wx.switchTab({url:'/pages/home/home'})},false)},
 mode(e){this.setData({mode:e.currentTarget.dataset.mode,error:''})},
 input(e){this.setData({[e.currentTarget.dataset.field]:e.detail.value})},
 submit(){return api.run(this,async()=>{
  if(this.data.mode==='create')await api.write('home.create',{name:this.data.name.trim()});
  else await api.write('home.join',{invite:this.data.invite.trim()});
  await api.ensure(false);wx.switchTab({url:'/pages/home/home'});
 })}, profile(){wx.switchTab({url:'/pages/profile/profile'})}
});