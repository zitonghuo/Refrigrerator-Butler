// Only explicit labels become suggestions. Never infer expiry from an arbitrary date.
function dateIn(value) {
  const m = value.match(/(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?/);
  if (!m) return '';
  const iso = m[1] + '-' + m[2].padStart(2, '0') + '-' + m[3].padStart(2, '0');
  const d = new Date(iso + 'T00:00:00Z');
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === iso ? iso : '';
}
module.exports = function parseLabel(lines) {
  const result = { name: '', production: '', shelfLife: '', expiry: '', text: lines.join('\n') };
  const unique = values => [...new Set(values.filter(Boolean))];
  const names = [], production = [], expiry = [], shelf = [];
  for (const line of lines) {
    const name = line.match(/^(?:产品名称|食品名称|品名)\s*[:：]\s*(.{1,80})$/);
    if (name) names.push(name[1].trim());
    if (/生产日期/.test(line)) production.push(dateIn(line));
    if (/有效期至|保质期至|到期日期/.test(line)) expiry.push(dateIn(line));
    const life = line.match(/保质期\s*[:：]?\s*(\d+\s*(?:天|日|个月|月|年))/);
    if (life) shelf.push(life[1]);
  }
  for (const [key, values] of Object.entries({ name: names, production, expiry, shelfLife: shelf })) {
    const candidates = unique(values); if (candidates.length === 1) result[key] = candidates[0];
  }
  return result;
};
