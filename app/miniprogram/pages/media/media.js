const api = require('../../utils/api');
const config = require('../../config');
const parseLabel = require('../../utils/label-parser');
const vision = require('../../utils/vision');
const invoke = (method, options) => new Promise((resolve, reject) => wx[method]({ ...options, success: resolve, fail: reject }));
Page({
  data: { cloudEnabled: config.mediaCloudEnabled === true, visionEnabled: vision.enabled(), loading: false, busy: false, error: '', items: [], local: null, selected: '', preview: null, suggestion: null, foods: null, confirmed: false, itemId: '', status: '' },
  onLoad(query) { this.setData({ itemId: query.itemId || '' }); },
  onShow() { this.refresh(); },
  onHide() { this.setData({ preview: null }); },
  onPullDownRefresh() { this.refresh(); },
  refresh() {
    if (!this.data.cloudEnabled) {
      this.setData({ loading: false, error: '', items: [] });
      wx.stopPullDownRefresh();
      return;
    }
    return api.load(this, () => this.fetch());
  },
  async fetch() { const result = await api.call('media.list', { itemId: this.data.itemId }); this.setData({ items: result.items }); },
  capture(e) {
    const kind = e.currentTarget.dataset.kind;
    return api.run(this, async () => {
      try {
        if (wx.requirePrivacyAuthorize) await invoke('requirePrivacyAuthorize', {});
        const result = await invoke('chooseMedia', { count: 1, mediaType: [kind], sourceType: ['camera', 'album'], maxDuration: 30, sizeType: ['compressed'], camera: 'back' });
        const f = result.tempFiles[0];
        if (!f || f.size > (kind === 'image' ? 4 : 12) * 1024 * 1024 || (kind === 'video' && f.duration > 30.5)) throw Error('照片最多 4 MB；视频最多 30 秒、12 MB，请缩短或压缩后选择。');
        this.uploadTask = null;
        this.setData({ local: { path: f.tempFilePath, size: f.size, kind }, preview: null, suggestion: null, foods: null, confirmed: false, selected: '', status: this.data.cloudEnabled ? '已选择，点击上传保存。' : '已选好，可以在此查看。当前为临时预览，不会上传或自动保存。' });
      } catch (error) {
        if (/cancel/.test(error.errMsg || '')) return;
        throw Error(error.message || '无法使用相机或相册，请检查微信权限后重试。');
      }
    });
  },
  saveLocal() {
    const local=this.data.local;if(!local)return;
    return api.run(this,async()=>{try {await invoke(local.kind==='image'?'saveImageToPhotosAlbum':'saveVideoToPhotosAlbum',{filePath:local.path});this.setData({status:'已保存到手机相册，退出页面后仍可在相册查看。'});wx.showToast({title:'已保存到相册'});}catch(e){throw Error(/auth|deny|denied/.test(e.errMsg||'')?'未获得相册保存权限，请在微信设置中允许后重试。':'保存未完成，请重试；原照片或视频不受影响。');}});
  },
  clearLocal() {
    if (this.data.busy) return;
    this.uploadTask = null;
    this.setData({ local: null, foods: null, suggestion: null, confirmed: false, selected: '', error: '', status: '' });
  },
  previewLocal() {
    const local = this.data.local;
    if (local && local.kind === 'image') wx.previewImage({ current: local.path, urls: [local.path] });
  },
  localError() { this.setData({ error: '这份临时文件无法预览，请重新拍摄或选择。' }); },
  manual() { wx.navigateTo({ url: '/pages/add/add' }); },
  upload() {
    if (!this.data.cloudEnabled) return;
    return api.run(this, async () => {
      const local = this.data.local; if (!local) return;
      // Keep one prepare key and fileID for retries in this page. Never re-upload after commit ambiguity.
      if (!this.uploadTask) this.uploadTask = { key: Date.now() + '-' + Math.random().toString(36).slice(2) };
      const task = this.uploadTask;
      if (!task.id) Object.assign(task, await api.call('media.prepare', { kind: local.kind, size: local.size, itemId: this.data.itemId }, task.key));
      this.setData({ status: '正在上传，请保持页面打开…' });
      if (!task.fileID) {
        const result = await wx.cloud.uploadFile({ cloudPath: task.path, filePath: local.path, config: { env: config.cloudEnv } });
        task.fileID = result.fileID;
      }
      const record = await api.call('media.commit', { id: task.id, fileID: task.fileID });
      this.setData({ local: null, selected: record.id, status: '已保存到家庭附件。', suggestion: null });
      this.uploadTask = null; await this.fetch();
    });
  },
  view(e) {
    return api.run(this, async () => {
      const id = e.currentTarget.dataset.id; const item = this.data.items.find(i => i.id === id);
      const result = await api.call('media.url', { id });
      this.setData({ preview: { ...item, url: result.url } });
    });
  },
  previewError() { this.setData({ preview: null, error: '预览链接可能已过期，请重新点击查看。' }); },
  recognize(e) {
    if (!this.data.cloudEnabled) return;
    return api.run(this, async () => {
      const id = e.currentTarget.dataset.id;
      this.setData({ selected: id, status: '正在识别包装文字…', suggestion: null, foods: null, confirmed: false });
      const result = await api.call('media.ocr', { id });
      this.setData({ suggestion: parseLabel(result.lines), status: '请对照包装核对。空白或冲突字段不会自动填写。' });
    });
  },
  recognizeFood(e) {
    if (!this.data.cloudEnabled) return;
    return api.run(this, async () => {
      const id = e.currentTarget.dataset.id;
      this.setData({ selected: id, status: '正在识别画面里的食材…', suggestion: null, foods: null, confirmed: false });
      const result = await api.call('media.recognize', { id });
      this.setData({ foods: result.candidates, status: result.candidates.length ? '识别完成，请核对后带入入库表单。' : '没有识别到食材，可以手动填写或换一张照片。' });
    });
  },
  recognizeGlm() {
    const local=this.data.local;if(!local||local.kind!=='image')return;
    return api.run(this,async()=>{
      if(!await api.ensure())return;
      const ready=await api.call('vision.status');if(!ready.ready)throw Error('智谱照片识别尚未配置，暂时可以手动录入。');
      const consent=await invoke('showModal',{title:'使用智谱识别照片',content:'本次压缩照片将经微信云函数发送给智谱开放平台（GLM-4V-Flash）处理。请避开人脸、证件等个人信息。识别可能出错，数量和日期需自行填写。是否发送？',confirmText:'同意发送'});
      if(!consent.confirm)return;
      this.setData({foods:null,suggestion:null,selected:'',confirmed:false,status:'正在识别，最多等待约半分钟…'});
      const foods=await require('../../utils/glm-vision').recognize(local.path,ready.consentVersion);
      this.setData({foods,status:foods.length?'请核对名称，数量、日期和存放位置需自行确认。':'未识别到明确食材，请手动填写。'});
    });
  },
  recognizeLocal() {
    const local = this.data.local;
    if (!local || local.kind !== 'image' || !this.data.visionEnabled) return;
    return api.run(this, async () => {
      const consent=await invoke('showModal',{title:'发送照片进行识别',content:'这张照片将发送到开发者配置的本机识别服务。是否继续？',confirmText:'发送识别'});if(!consent.confirm)return;
      this.setData({ status: '正在用本机模型识别…', foods: null, suggestion: null, confirmed: false });
      const foods = await vision.recognize(local.path);
      this.setData({ foods, status: foods.length ? '识别完成，请核对后带入入库表单。' : '没有识别到食材，可以手动填写或换一张照片。' });
    });
  },
  useFoods() {
    if(!this.data.confirmed){this.setData({error:'请先核对候选名称。'});return;}
    const auth = api.current(); if (!auth || !this.data.foods || !this.data.foods.length) return;
    const existing = wx.getStorageSync('add-draft-v2');
    let rows = existing && existing.uid === auth.user.id && existing.homeId === auth.user.homeId ? existing.rows : [];
    // A photo can only be bound to the first new batch; further candidates are manual rows.
    const photo = this.data.items.find(i => i.id === this.data.selected);
    rows = rows.filter(row => (row.name || row.mediaId) && row.mediaId !== this.data.selected);
    if (rows.length + this.data.foods.length > 20) { this.setData({ error: '草稿最多 20 项，请先保存已有食材。' }); return; }
    this.data.foods.forEach((food, index) => rows.push({
      name: food.name,
      quantity: food.quantity ? String(food.quantity) : '',
      unit: food.unit,
      location: food.location,
      expiry: food.expiry,
      source: food.source,
      ...(photo && !photo.itemId && index === 0 ? { mediaId: photo.id } : {})
    }));
    wx.setStorageSync('add-draft-v2', { uid: auth.user.id, homeId: auth.user.homeId, rows });
    wx.redirectTo({ url: '/pages/add/add' });
  },
  field(e) { this.setData({ ['suggestion.' + e.currentTarget.dataset.field]: e.detail.value, confirmed: false }); },
  agreement(e) { this.setData({ confirmed: e.detail.value.includes('checked') }); },
  use() {
    if (!this.data.confirmed) { this.setData({ error: '请先对照包装确认识别结果。' }); return; }
    const auth = api.current(); if (!auth || !this.data.suggestion) return;
    const s = this.data.suggestion;
    const existing = wx.getStorageSync('add-draft-v2');
    let rows = existing && existing.uid === auth.user.id && existing.homeId === auth.user.homeId ? existing.rows : [];
    rows = rows.filter(row => (row.name || row.mediaId) && row.mediaId !== this.data.selected);
    if (rows.length >= 20) { this.setData({ error: '草稿已满 20 项，请先保存已有食材。' }); return; }
    // Existing item photos are for reference; only unbound photos can become new batches.
    const photo = this.data.items.find(i => i.id === this.data.selected);
    rows.push({ name: s.name, quantity: '1', unit: '个', location: '冷藏', expiry: s.expiry, source: 'label', ...(photo && !photo.itemId ? { mediaId: photo.id } : {}) });
    wx.setStorageSync('add-draft-v2', { uid: auth.user.id, homeId: auth.user.homeId, rows });
    wx.redirectTo({ url: '/pages/add/add' });
  },
  remove(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({ title: '删除附件', content: '从家庭照片与视频中移除该附件？', success: r => {
      if (r.confirm) api.run(this, async () => { await api.call('media.remove', { id }); this.setData({ preview: null, suggestion: null }); await this.fetch(); });
    } });
  }
});
