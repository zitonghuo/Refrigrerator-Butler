const api=require('../../utils/api');
const results={sending:'上一条提醒正在处理；如果结果不确定，不会自动重发',sent:'上次已提交微信发送',rejected:'微信未允许发送，请重新订阅',failed:'上次发送失败，请重新订阅',unknown:'上次发送结果未确认，为避免重复未自动重发',cancelled:'已取消提醒',expired:'订阅登记已过期或家庭已变更'};
Page({data:{loading:false,busy:false,error:'',ready:false,templateId:'',pending:false,lastText:''},onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
refresh(){return api.load(this,async()=>{const s=await api.call('reminder.status');this.setData({...s,lastText:results[s.lastResult]||''})})},
subscribe(){
 if(this.data.busy||this.data.loading||!this.data.ready)return;
 if(!wx.requestSubscribeMessage){this.setData({error:'当前微信版本不支持订阅消息，请升级微信。'});return}
 // Call directly in the tap handler; do not await a server request before opening the native consent dialog.
 this.setData({busy:true,error:''});
 wx.requestSubscribeMessage({tmplIds:[this.data.templateId],success:async result=>{
  try{if(result[this.data.templateId]!=='accept'){this.setData({error:'你未同意订阅，不影响继续使用冰箱。'});return}
   const s=await api.write('reminder.subscribe',{templateId:this.data.templateId,accepted:true});this.setData({...s,lastText:''});wx.showToast({title:'已登记一次提醒'});
  }catch(e){this.setData({error:e.message+'；若有未确认操作，可到个人中心恢复提交。'})}finally{this.setData({busy:false})}
 },fail:()=>this.setData({busy:false,error:'未能打开微信订阅窗口，请在手机微信中重试。'})});
},cancel(){return api.run(this,async()=>{await api.write('reminder.cancel',{});this.setData({pending:false,lastText:'已取消待发送提醒'})})}});
