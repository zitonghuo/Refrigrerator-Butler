const { prepareFood } = require('./food-units');

// Keep the printed text beside the editable candidate. Never expand an uncertain word.
function receiptRows(lines) {
  const rows = [];
  let inTable = false;
  for (const raw of lines) {
    const line = raw.normalize('NFKC').trim().replace(/([\u3400-\u9fff])\s+(?=[\u3400-\u9fff])/g, '$1');
    if (rows.length && line === '小计') break;
    if (/^(?:合计|总计|应付|实付|件数|支付方式|找零|收款金额)/.test(line)) break;
    if (/品名|商品名称|数量|单价/.test(line) && !/\d{4}/.test(line)) { inTable = true; continue; }
    if (/^(?:收银|时间|日期|门店|电话|地址|机号|会员|小计|优惠)/.test(line)) continue;
    // OCR may insert punctuation or spaces inside a SKU. Only strip a numeric
    // prefix when it contains enough digits to be an item code.
    const sku = line.match(/((?:\d[\s.,:;'’〔〕?？-]*){4,})([\u3400-\u9fffA-Za-z].*)$/);
    const coded = Boolean(sku);
    if (!coded && !inTable) continue;
    if (!coded && /^[^\u3400-\u9fffA-Za-z]*[?'’:]/.test(line)) continue;
    const name = (coded ? sku[2] : line).split(/\s+\d+[.,]\d{2,3}(?:\s|$)/)[0].trim().replace(/[.,。，]+$/, '');
    if (!/[\u3400-\u9fffA-Za-z]/.test(name) || name.length > 80 || /^[\d\s:.,?'-]+$/.test(name)) continue;
    rows.push({ ...prepareFood({ name, quantity: null, location: '冷藏', expiry: '', source: 'manual' }), receiptLine: raw.slice(0,160) });
    if (rows.length === 20) break;
  }
  return rows;
}

async function recognizeReceipt(path) {
  if (typeof wx.createVKSession !== 'function' || typeof wx.createOffscreenCanvas !== 'function') {
    throw Error('OCR unavailable');
  }
  const canvas = wx.createOffscreenCanvas({ type: '2d', width: 1, height: 1 });
  const img = canvas.createImage();
  await new Promise((resolve,reject) => { img.onload=resolve; img.onerror=reject; img.src=path; });
  const scale = Math.min(1.5, 2200/Math.max(img.width,img.height));
  const width = canvas.width = Math.max(1,Math.round(img.width*scale));
  const height = canvas.height = Math.max(1,Math.round(img.height*scale));
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img,0,0,width,height);
  const pixels = ctx.getImageData(0,0,width,height).data;
  const gl = wx.createOffscreenCanvas({type:'webgl',width:1,height:1}).getContext('webgl');
  const session = wx.createVKSession({version:'v1',track:{OCR:{mode:2}},gl});
  return new Promise((resolve,reject) => {
    let done = false;
    const finish = (error,rows) => {
      if(done)return;
      done=true; clearTimeout(timer);
      try { session.stop(); } catch {}
      try { session.destroy(); } catch {}
      if(error)reject(error); else resolve(rows);
    };
    const timer = setTimeout(()=>finish(Error('OCR timeout')),12000);
    session.start(err=>{
      if(done)return;
      if(err)return finish(Error('OCR unavailable'));
      try {
        session.on('updateAnchors',anchors=>{
          if(done)return;
          try {
            const text=anchors.map(a=>a.text || '').filter(Boolean);
            const lines = text.join('\n').split(/\r?\n/);
            finish(null,receiptRows(lines));
          } catch(error){finish(error);}
        });
        session.runOCR({frameBuffer:pixels.buffer,width,height});
      } catch(error){finish(error);}
    });
  });
}
module.exports = { recognizeReceipt, receiptRows };
