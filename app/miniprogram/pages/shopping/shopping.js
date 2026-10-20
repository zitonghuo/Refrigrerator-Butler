const api=require('../../utils/api');
Page({data:{loading:false,busy:false,error:'',name:'',items:[],pending:0},onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
 async fetch(){const s=await api.call('snapshot');this.setData({items:s.shopping,pending:s.shopping.filter(i=>!i.done).length})},refresh(){return api.load(this,()=>this.fetch())},
 input(e){this.setData({name:e.detail.value})},add(){return api.run(this,async()=>{await api.write('shopping.add',{name:this.data.name.trim()});this.setData({name:''});await this.fetch()})},
 toggle(e){const item=this.data.items.find(i=>i.id===e.currentTarget.dataset.id);return api.run(this,async()=>{await api.write('shopping.set',{id:item.id,version:item.version,done:!item.done});await this.fetch()})},
 remove(e){const item=this.data.items.find(i=>i.id===e.currentTarget.dataset.id);wx.showModal({title:'删除采购项',content:'删除“'+item.name+'”？',success:r=>{if(r.confirm)api.run(this,async()=>{await api.write('shopping.remove',{id:item.id,version:item.version});await this.fetch()})}})}
});