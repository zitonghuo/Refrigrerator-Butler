const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const mini = path.join(root, 'miniprogram');
const app = JSON.parse(fs.readFileSync(path.join(mini, 'app.json')));
const config = require(path.join(mini, 'config.js'));
const failures = [];
for (const route of app.pages) {
  for (const ext of ['js', 'json', 'wxml']) if (!fs.existsSync(path.join(mini, route + '.' + ext))) failures.push('Missing ' + route + '.' + ext);
  let definition;
  const source = fs.readFileSync(path.join(mini, route + '.js'), 'utf8');
  new vm.Script(source, { filename: route });
  vm.runInNewContext(source, { Page: value => { definition = value; }, require: p => p.endsWith('config') ? config : {}, wx: {} });
  const wxml = fs.readFileSync(path.join(mini, route + '.wxml'), 'utf8');
  for (const [, method] of wxml.matchAll(/bind(?:tap|input|change)="([\w]+)"/g)) if (typeof definition[method] !== 'function') failures.push(route + ': missing handler ' + method);
  for (const match of source.matchAll(/\/pages\/[a-z]+\/[a-z]+/g)) if (!app.pages.includes(match[0].slice(1))) failures.push('Unknown route ' + match[0]);
}
for (const item of app.tabBar.list) if (!app.pages.includes(item.pagePath)) failures.push('Unknown tab ' + item.pagePath);
const rules = JSON.parse(fs.readFileSync(path.join(root, 'database/security-rules.json')));
if (rules.read !== false || rules.write !== false) failures.push('Database rules must deny direct client access');
const project = JSON.parse(fs.readFileSync(path.join(root, 'project.config.json')));
if (project.appid !== config.appId || !project.setting.urlCheck) failures.push('Invalid production project config');
if (process.argv.includes('--release')) {
  const release = JSON.parse(fs.readFileSync(path.join(root, 'release.json')));
  if (!config.cloudEnv || /placeholder|待填写|your-/i.test(config.cloudEnv)) failures.push('Cloud environment ID is not configured');
  if (!release.registeredOperator) failures.push('Confirm the registered operator shown in WeChat (team name is not necessarily account subject)');
  if (!release.cloudRegion) failures.push('Confirm the deployed cloud region');
  for (const [name, value] of Object.entries(release.verified)) if (value !== true) failures.push('Not verified: ' + name);
}
if (failures.length) { console.error(failures.join('\n')); process.exitCode = 1; }
else console.log('PASS: ' + app.pages.length + ' pages, all actions/routes, deny-all rules and project configuration');
