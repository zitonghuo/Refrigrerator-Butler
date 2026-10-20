const api=require('../../utils/api');
const blank=()=>({name:'',quantity:'1',unit:'个',location:'冷藏',expiry:'',source:'manual'});
Page({media(){wx.navigateTo({url:'/pages/media/media'})},data:{loading:false,busy:false,error:'',rows:[blank()],locations:['冷藏','冷冻','常温'],sources:['手动填写','包装标注','自行估算'],sourceLabels:{manual:'手动填写',label:'包装标注',estimate:'自行估算'}},
 onShow(){api.load(this,async auth=>{const draft=wx.getStorageSync('add-draft-v2');if(draft&&draft.uid===auth.user.id&&draft.homeId===auth.user.homeId)this.setData({rows:draft.rows});this.auth=auth})},
 persist(){if(this.auth)wx.setStorageSync('add-draft-v2',{uid:this.auth.user.id,homeId:this.auth.user.homeId,rows:this.data.rows})},
 input(e){this.setData({['rows['+e.currentTarget.dataset.index+'].'+e.currentTarget.dataset.field]:e.detail.value});this.persist()},
 location(e){this.setData({['rows['+e.currentTarget.dataset.index+'].location']:this.data.locations[+e.detail.value]});this.persist()},
 source(e){this.setData({['rows['+e.currentTarget.dataset.index+'].source']:['manual','label','estimate'][+e.detail.value]});this.persist()},
 clearDate(e){this.setData({['rows['+e.currentTarget.dataset.index+'].expiry']:''});this.persist()},
 addRow(){if(this.data.rows.length<20){this.setData({rows:[...this.data.rows,blank()]});this.persist()}},
 remove(e){const rows=this.data.rows.filter((_,i)=>i!==+e.currentTarget.dataset.index);this.setData({rows:rows.length?rows:[blank()]});this.persist()},
 save(){return api.run(this,async()=>{await api.write('item.add',{items:this.data.rows});wx.removeStorageSync('add-draft-v2');this.setData({rows:[blank()]});wx.showToast({title:'已入库'});wx.switchTab({url:'/pages/home/home'})})}
});