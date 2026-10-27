'use strict';
const crypto=require('node:crypto');
const {band}=require('./insights');
const POLICY='2026-10-27-reminders';
const DAY=86400000;
function settings(env={}) {
  let fields;try{fields=JSON.parse(env.REMINDER_FIELDS||'{}')}catch{return {ready:false}}
  const templateId=env.REMINDER_TEMPLATE_ID||'';
  const ready=env.REMINDERS_READY==='true' && /^[\w-]{10,128}$/.test(templateId) && /^thing\d+$/.test(fields.name||'') && /^(date|time)\d+$/.test(fields.date||'') && (!fields.note || /^thing\d+$/.test(fields.note)) && new Set(Object.values(fields)).size===Object.values(fields).length;
  return {ready,templateId,fields,state:['developer','trial','formal'].includes(env.REMINDER_STATE)?env.REMINDER_STATE:'formal'};
}
function status(user,config,now) {
  const r=user.reminder||{};
  return {ready:!!config.ready,templateId:config.ready?config.templateId:'',pending:r.state==='pending'&&r.expiresAt>now&&r.homeId===user.homeId,expiresAt:r.expiresAt||0,lastResult:r.state==='sending'?'sending':r.result||'',lastAt:r.finishedAt||0};
}
// Only platform/admin timer invocations may dispatch; event.Type alone is never authorization.
function trustedTimer(event,context={}) {return !!event&&event.Type==='Timer'&&!['OPENID','FROM_OPENID','UNIONID','UID','APPID'].some(k=>context[k]);}
function createDispatcher({store,listUserIds,send,config,clock=Date.now}) {
  return async(event,context)=>{
    if(!trustedTimer(event,context))return {ok:false,error:'FORBIDDEN'};
    if(!config.ready)return {ok:false,error:'REMINDER_SETUP'};
    const hour=new Date(clock()+8*3600000).getUTCHours();
    if(hour<9||hour>20)return {ok:true,skipped:'QUIET_HOURS'};
    let cursor='',sent=0,claimed=0;
    for(let page=0;page<50;page++) {
      const ids=await listUserIds(cursor);if(!ids.length)break;
      for(const id of ids) {
        const claim=await store.transaction(async tx=>{
          const u=await tx.get('fridge_users',id);const r=u&&u.reminder;
          if(r&&r.state==='sending'&&clock()-r.claimedAt>15*60000){u.reminder={state:'off',result:'unknown',finishedAt:clock(),lastSentDay:r.lastSentDay||''};await tx.put('fridge_users',id,u);return null;}
          if(!r||r.state!=='pending')return null;
          const now=clock();const home=u.homeId&&await tx.get('fridge_homes',u.homeId);
          if(u.policyVersion!==POLICY||r.expiresAt<=now||!home||r.homeId!==u.homeId||!home.members.some(m=>m.id===id)||r.templateId!==config.templateId) {
            u.reminder={state:'off',result:'expired',finishedAt:now};await tx.put('fridge_users',id,u);return null;
          }
          const foods=home.items.filter(i=>i.quantity>0&&['urgent','soon'].includes(band(i.expiry,now))).sort((a,b)=>a.expiry.localeCompare(b.expiry));
          if(!foods.length)return null;
          if(r.lastSentDay===new Date(now+8*3600000).toISOString().slice(0,10))return null;
          const claimId=crypto.randomBytes(16).toString('hex');
          u.reminder={...r,state:'sending',claimId,claimedAt:now};await tx.put('fridge_users',id,u);
          return {claimId,openid:r.openid,homeId:u.homeId,expiry:foods[0].expiry};
        });
        if(!claim)continue;claimed++;
        // Recheck cancellation/membership just before calling WeChat. The message itself contains no inventory names.
        const valid=await store.transaction(async tx=>{const u=await tx.get('fridge_users',id);const h=u&&u.homeId&&await tx.get('fridge_homes',u.homeId);return !!(u&&u.reminder&&u.reminder.claimId===claim.claimId&&u.reminder.state==='sending'&&u.homeId===claim.homeId&&h&&h.members.some(m=>m.id===id))});
        let result='cancelled';
        if(valid){
          const data={};data[config.fields.name]={value:'冰箱临期食材'};data[config.fields.date]={value:claim.expiry};if(config.fields.note)data[config.fields.note]={value:'请打开小程序查看并安排食用'};
          try{const out=await send({touser:claim.openid,templateId:config.templateId,page:'pages/today/today',data,miniprogramState:config.state,lang:'zh_CN'});const code=Number(out.errCode??out.errcode??0);result=code===0?'sent':code===43101?'rejected':'failed';if(result==='sent')sent++;}catch{result='unknown'}
        }
        await store.transaction(async tx=>{const u=await tx.get('fridge_users',id);if(!u||!u.reminder||u.reminder.claimId!==claim.claimId)return;u.reminder={state:'off',result,finishedAt:clock(),lastSentDay:result==='sent'?new Date(clock()+8*3600000).toISOString().slice(0,10):u.reminder.lastSentDay||''};await tx.put('fridge_users',id,u)});
      }
      cursor=ids[ids.length-1];
    }
    return {ok:true,sent,claimed};
  };
}
module.exports={settings,status,trustedTimer,createDispatcher};
