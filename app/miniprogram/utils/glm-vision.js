const api=require('./api');
const invoke=(name,options)=>new Promise((resolve,reject)=>wx[name]({...options,success:resolve,fail:reject}));
async function recognize(path,consentVersion){
 let file=path;
 for(const quality of [60,35,15]){
  const result=await invoke('compressImage',{src:path,quality,compressedWidth:1280});file=result.tempFilePath;
  const data=await new Promise((resolve,reject)=>wx.getFileSystemManager().readFile({filePath:file,encoding:'base64',success:r=>resolve(r.data),fail:reject}));
  if(data.length<=Math.floor(500*1024/3)*4){
   const result=await api.call('vision.recognize',{imageBase64:data,consentVersion});return result.candidates;
  }
 }
 throw Error('压缩后仍超过 500 KB，请裁剪照片或重新拍摄。');
}
module.exports={recognize};
