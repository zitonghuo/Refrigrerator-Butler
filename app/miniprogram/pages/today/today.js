const api=require('../../utils/api');
Page({data:{loading:false,busy:false,error:'',groups:[],shopping:[],empty:false},
onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
refresh(){return api.load(this,async()=>{const s=await api.call('todo.list');this.setData({groups:[{name:'已过期 · 请检查处理',items:s.expired},{name:'今天到期 · 优先安排',items:s.urgent},{name:'3 天内到期',items:s.soon}],shopping:s.shopping,empty:!s.expired.length&&!s.urgent.length&&!s.soon.length&&!s.shopping.length})})},
detail(e){wx.navigateTo({url:'/pages/detail/detail?id='+encodeURIComponent(e.currentTarget.dataset.id)})},shopping(){wx.switchTab({url:'/pages/shopping/shopping'})},reminders(){wx.navigateTo({url:'/pages/reminders/reminders'})},recipes(){wx.navigateTo({url:'/pages/recipes/recipes'})}});
