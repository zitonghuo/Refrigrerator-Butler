const api=require('../../utils/api');
const labels={in:'入库',consume:'消耗',discard:'丢弃',adjust:'盘点调整',nearExpiryConsumed:'临期食材消耗'};
const units=b=>b?Object.entries(b.units||{}).map(([u,n])=>n+' '+u).join('、')||'0':'暂无完整记录';
Page({data:{loading:false,busy:false,error:'',days:7,report:null,totals:[],daily:[]},onShow(){this.refresh()},onPullDownRefresh(){this.refresh()},
period(e){if(this.data.loading)return;this.setData({days:Number(e.currentTarget.dataset.days)});this.refresh()},
refresh(){return api.load(this,async()=>{const r=await api.call('report.summary',{days:this.data.days});this.setData({report:r,totals:Object.keys(labels).map(k=>({name:labels[k],count:r.totals[k]?r.totals[k].count:null,text:units(r.totals[k])})),daily:r.byDay.map(d=>({date:d.date,text:['in','consume','discard','adjust'].filter(k=>d[k]&&d[k].count).map(k=>labels[k]+' '+units(d[k])).join('；')||'暂无记录'}))})})}});
