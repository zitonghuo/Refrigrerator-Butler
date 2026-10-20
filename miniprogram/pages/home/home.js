const labels={expired:'已过期',urgent:'24 小时内',soon:'3 天内',week:'7 天内',fresh:'安心存放',unknown:'待补日期'};
const sourceLabels={manual:'手动填写',label:'标签读取',estimate:'估算日期'};
const blank=()=>({name:'',quantity:'1',unit:'个',location:'冷藏',expiry:'',source:'manual'});
Page({
 data:{logged:false,authMode:'create',form:{name:'',homeName:'我们的小厨房',invite:'',code:''},tab:'inventory',filter:'全部',filters:['全部','冷藏','冷冻','常温'],locations:['冷藏','冷冻','常温'],sourceNames:['手动填写','标签读取','估算日期'],state:null,visible:[],candidates:[blank()],shoppingName:'',error:'',taskStatus:'',busy:false,urgentCount:0,sourceLabels},
 onLoad(){this.token=wx.getStorageSync('fridge-token');if(this.token)this.refresh()},
 onShow(){if(this.token&&this.data.state)this.refresh()},
 onUnload(){clearTimeout(this.timer)},
 request(path,data){return new Promise((resolve,reject)=>wx.request({url:getApp().globalData.baseUrl+'/api/'+path,method:data?'POST':'GET',data,header:{'content-type':'application/json',Authorization:'Bearer '+(this.token||'')},timeout:30000,success:r=>{if(r.statusCode===401){this.setData({logged:false});wx.removeStorageSync('fridge-token')}r.statusCode>=200&&r.statusCode<300?resolve(r.data):reject(Error(r.data.error||'请求失败'))},fail:()=>reject(Error('无法连接后端，请检查服务地址和启动状态'))}))},
 async refresh(){try{const state=await this.request('state');state.items=state.items.map(x=>({...x,label:labels[x.band],sourceLabel:sourceLabels[x.source]}));this.setData({state,logged:true,error:'',urgentCount:state.items.filter(x=>['urgent','soon'].includes(x.band)).length});this.filterItems()}catch(e){this.setData({error:e.message})}},
 filterItems(){this.setData({visible:this.data.state.items.filter(x=>(this.data.filter==='全部'||x.location===this.data.filter)&&(this.data.tab!=='urgent'||['expired','urgent','soon','week'].includes(x.band)))})},
 authMode(e){this.setData({authMode:e.currentTarget.dataset.mode,error:''})},
 field(e){this.setData({['form.'+e.currentTarget.dataset.field]:e.detail.value})},
 async authenticate(){this.setData({busy:true,error:''});try{const r=await this.request('auth',{action:this.data.authMode,...this.data.form});this.token=r.token;wx.setStorageSync('fridge-token',r.token);await this.refresh();if(r.recoveryCode)wx.showModal({title:'请保存个人恢复码',content:r.recoveryCode,confirmText:'复制恢复码',showCancel:false,success:()=>wx.setClipboardData({data:r.recoveryCode})})}catch(e){this.setData({error:e.message})}finally{this.setData({busy:false})}},
 tab(e){this.setData({tab:e.currentTarget.dataset.tab,error:''});if(this.data.tab==='add'){this.key=this.key||Date.now()+'-'+Math.random();const task=wx.getStorageSync('fridge-task');if(task)this.poll(task)}else this.filterItems()},
 filter(e){this.setData({filter:e.currentTarget.dataset.filter});this.filterItems()},
 candidate(e){this.setData({['candidates['+e.currentTarget.dataset.index+'].'+e.currentTarget.dataset.field]:e.detail.value})},
 location(e){this.setData({['candidates['+e.currentTarget.dataset.index+'].location']:this.data.locations[+e.detail.value]})},
 source(e){this.setData({['candidates['+e.currentTarget.dataset.index+'].source']:['manual','label','estimate'][+e.detail.value]})},
 addRow(){this.setData({candidates:[...this.data.candidates,blank()]})},
 removeRow(e){this.setData({candidates:this.data.candidates.filter((_,i)=>i!==+e.currentTarget.dataset.index)})},
 async save(){this.setData({busy:true,error:''});try{this.key=this.key||Date.now()+'-'+Math.random();await this.request('items/add',{key:this.key,items:this.data.candidates});this.key=null;this.setData({tab:'inventory',candidates:[blank()]});await this.refresh();wx.showToast({title:'已入库'})}catch(e){this.setData({error:e.message})}finally{this.setData({busy:false})}},
 manage(e){const item=this.data.state.items.find(x=>x.id===e.currentTarget.dataset.id);wx.showActionSheet({itemList:['消耗','丢弃','盘点剩余量'],success:r=>{const kind=['消耗','丢弃','盘点'][r.tapIndex];wx.showModal({title:kind==='盘点'?'填写现在剩余数量':'填写本次'+kind+'数量',editable:true,placeholderText:String(item.quantity),success:async res=>{if(!res.confirm)return;try{await this.request('items/change',{id:item.id,version:item.version,kind,quantity:res.content});await this.refresh();wx.showToast({title:'已更新'})}catch(e){wx.showModal({title:'未保存',content:e.message,showCancel:false});this.refresh()}}})}})},
 shoppingInput(e){this.setData({shoppingName:e.detail.value})},
 async addShopping(){try{await this.request('shopping/add',{name:this.data.shoppingName});this.setData({shoppingName:''});this.refresh()}catch(e){this.setData({error:e.message})}},
 async toggleShopping(e){try{await this.request('shopping/toggle',{id:e.currentTarget.dataset.id});this.refresh()}catch(e){this.setData({error:e.message})}},
 async demo(){try{await this.request('demo',{});this.refresh()}catch(e){this.setData({error:e.message})}},
 copyInvite(){wx.setClipboardData({data:this.data.state.home.invite})},
 async rotateInvite(){try{await this.request('invite/rotate',{});this.refresh()}catch(e){this.setData({error:e.message})}},
 async logout(){try{await this.request('logout',{})}catch{}wx.removeStorageSync('fridge-token');this.token=null;this.setData({logged:false,state:null,error:''})},
 choose(e){const kind=e.currentTarget.dataset.kind;wx.chooseMedia({count:1,mediaType:kind==='video'?['video']:['image'],maxDuration:30,success:r=>{const file=r.tempFiles[0];if(file.size>20*1024*1024){wx.showToast({title:'文件超过 20 MB',icon:'none'});return}this.setData({taskStatus:'正在上传…',busy:true});wx.getFileSystemManager().readFile({filePath:file.tempFilePath,encoding:'base64',success:async data=>{try{const t=await this.request('recognize',{kind,data:data.data});wx.setStorageSync('fridge-task',t.id);this.poll(t.id)}catch(e){this.setData({taskStatus:e.message,busy:false})}},fail:()=>this.setData({taskStatus:'文件读取失败，请重新选择',busy:false})})}})},
 async poll(id){clearTimeout(this.timer);try{const t=await this.request('task?id='+encodeURIComponent(id));if(t.status==='done'){this.setData({candidates:t.result,taskStatus:'识别完成，请逐项确认再入库。',busy:false});wx.removeStorageSync('fridge-task')}else if(t.status==='failed'){this.setData({taskStatus:t.error,busy:false});wx.removeStorageSync('fridge-task')}else{this.setData({taskStatus:'识别中…',busy:true});this.timer=setTimeout(()=>this.poll(id),1500)}}catch(e){this.setData({taskStatus:e.message,busy:false})}}
})
