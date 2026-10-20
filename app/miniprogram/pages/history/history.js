const api=require('../../utils/api');
Page({
  data: { loading: false, busy: false, error: '', events: [] },
  onShow() { this.refresh(); },
  onPullDownRefresh() { this.refresh(); },
  refresh() {
    return api.load(this, async () => {
      const state = await api.call('snapshot');
      this.setData({ events: state.events.map(event => ({ ...event, time: new Date(event.createdAt).toLocaleString() })) });
    });
  }
});
