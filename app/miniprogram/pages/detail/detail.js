const api=require('../../utils/api');
Page({media(){wx.navigateTo({url:'/pages/media/media?itemId='+encodeURIComponent(this.id)})},data:{loading:false,busy:false,error:'',item:null,events:[],editing:false,form:{},locations:['冷藏','冷冻','常温']},
 onLoad(q){this.id=q.id},onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
 async fetch(){const s=await api.call('item.get',{id:this.id});this.setData({item:api.decorate(s.item),form:{...s.item},events:s.events.map(e=>({...e,time:new Date(e.createdAt).toLocaleString()}))})},
 refresh(){return api.load(this,()=>this.fetch())},
 edit(){this.setData({editing:!this.data.editing,form:{...this.data.item}})},input(e){this.setData({['form.'+e.currentTarget.dataset.field]:e.detail.value})},
 location(e){this.setData({'form.location':this.data.locations[+e.detail.value]})},clearDate(){this.setData({'form.expiry':''})},
 save(){return api.run(this,async()=>{await api.write('item.update',{...this.data.form,id:this.id,version:this.data.item.version});this.setData({editing:false});await this.fetch();wx.showToast({title:'已保存'})})},
 change(e){const kind=e.currentTarget.dataset.kind;wx.showModal({title:kind==='盘点'?'当前剩余数量':'本次'+kind+'数量',editable:true,placeholderText:'当前 '+this.data.item.quantity+' '+this.data.item.unit,success:r=>{if(!r.confirm)return;api.run(this,async()=>{await api.write('item.change',{id:this.id,version:this.data.item.version,kind,quantity:r.content});wx.showToast({title:'已记录'});wx.navigateBack()})}})}
});