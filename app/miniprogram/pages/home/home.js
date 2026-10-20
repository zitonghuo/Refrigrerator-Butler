const api=require('../../utils/api');
Page({data:{loading:false,busy:false,error:'',home:null,items:[],visible:[],zones:[],filter:'全部',query:'',urgentOnly:false,urgent:0,expired:0,pending:0},
 onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
 refresh(){return api.load(this,async()=>{const s=await api.call('snapshot');const items=s.items.map(api.decorate);
  this.setData({home:s.home,items,zones:['全部','冷藏','冷冻','常温'].map(name=>({name,count:items.filter(i=>name==='全部'||i.location===name).length})),urgent:items.filter(i=>['urgent','soon'].includes(i.band)).length,expired:items.filter(i=>i.band==='expired').length,pending:s.shopping.filter(i=>!i.done).length});this.filterItems();})},
 filterItems(){this.setData({visible:this.data.items.filter(i=>(this.data.filter==='全部'||i.location===this.data.filter)&&(!this.data.urgentOnly||['expired','urgent','soon'].includes(i.band))&&i.name.toLowerCase().includes(this.data.query.trim().toLowerCase()))})},
 search(e){this.setData({query:e.detail.value});this.filterItems()},filter(e){this.setData({filter:e.currentTarget.dataset.name});this.filterItems()},urgent(){this.setData({urgentOnly:!this.data.urgentOnly});this.filterItems()},
 clear(){this.setData({query:'',filter:'全部',urgentOnly:false});this.filterItems()},
 add(){wx.navigateTo({url:'/pages/add/add'})},detail(e){wx.navigateTo({url:'/pages/detail/detail?id='+encodeURIComponent(e.currentTarget.dataset.id)})}
});