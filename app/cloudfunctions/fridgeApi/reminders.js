'use strict';
const crypto=require('node:crypto');
const {band}=require('./insights');
const POLICY='2026-10-27-reminders';
const DAY=86400000;
const TEMPLATE_ID='32QIb8xFekpH1mRqQIyvW34qzzmgoyJtYFaFHDtdl-w';
const TEMPLATE_FIELDS={name:'thing1',date:'time2',quantity:'character_string5',days:'number6',note:'thing3'};
function settings(env={}) {
  const templateId=env.REMINDER_TEMPLATE_ID||TEMPLATE_ID;
  let fields;try{fields=env.REMINDER_FIELDS?JSON.parse(env.REMINDER_FIELDS):(templateId===TEMPLATE_ID?TEMPLATE_FIELDS:{})}catch{return {ready:false}}
  if(!fields||typeof fields!=='object'||Array.isArray(fields))return {ready:false};
  const ready=env.REMINDERS_READY==='true' && /^[\w-]{10,128}$/.test(templateId) && /^thing\d+$/.test(fields.name||'') && /^(date|time)\d+$/.test(fields.date||'') && (!fields.note || /^thing\d+$/.test(fields.note)) && (!fields.quantity || /^character_string\d+$/.test(fields.quantity)) && (!fields.days || /^number\d+$/.test(fields.days)) && (templateId!==TEMPLATE_ID || Object.keys(TEMPLATE_FIELDS).every(key=>fields[key]===TEMPLATE_FIELDS[key])) && new Set(Object.values(fields)).size===Object.values(fields).length;
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
          const today=new Date(now+8*3600000).toISOString().slice(0,10);
          return {claimId,openid:r.openid,homeId:u.homeId,expiry:foods[0].expiry,batches:foods.length,days:Math.max(0,Math.round((Date.parse(foods[0].expiry)-Date.parse(today))/DAY))};
        });
        if(!claim)continue;claimed++;
        // Recheck cancellation/membership just before calling WeChat. The message itself contains no inventory names.
        const valid=await store.transaction(async tx=>{const u=await tx.get('fridge_users',id);const h=u&&u.homeId&&await tx.get('fridge_homes',u.homeId);return !!(u&&u.reminder&&u.reminder.claimId===claim.claimId&&u.reminder.state==='sending'&&u.homeId===claim.homeId&&h&&h.members.some(m=>m.id===id))});
        let result='cancelled';
        if(valid){
          const data={};data[config.fields.name]={value:'冰箱临期食材'};data[config.fields.date]={value:claim.expiry};if(config.fields.note)data[config.fields.note]={value:'请打开小程序查看并安排食用'};
          if(config.fields.quantity){data[config.fields.quantity]={value:String(claim.batches)};if(config.fields.note)data[config.fields.note]={value:'数量按临期批次计，请及时查看'};}
          if(config.fields.days)data[config.fields.days]={value:String(claim.days)};
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
