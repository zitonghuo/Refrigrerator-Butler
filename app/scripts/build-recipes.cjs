#!/usr/bin/env node
'use strict';
// Builds cloudfunctions/fridgeApi/recipes.json from the HowToCook markdown corpus.
// Source: https://github.com/Anduin2017/HowToCook (Unlicense / public domain)
// Usage: node scripts/build-recipes.cjs <HowToCook-dir>
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const SOURCE = process.argv[2] || process.env.HOWTOCOOK_DIR;
if (!SOURCE || !fs.existsSync(path.join(SOURCE, 'dishes'))) {
  console.error('Usage: node scripts/build-recipes.cjs <HowToCook checkout>');
  process.exit(1);
}

const ROOT = path.join(SOURCE, 'dishes');
const OUT = path.join(__dirname, '..', 'cloudfunctions', 'fridgeApi', 'recipes.json');
const CATEGORIES = {
  vegetable_dish: { label: '素菜', minutes: 15 },
  meat_dish: { label: '荤菜', minutes: 20 },
  aquatic: { label: '水产', minutes: 25 },
  soup: { label: '汤', minutes: 25 },
  staple: { label: '主食', minutes: 20 },
  breakfast: { label: '早餐', minutes: 10 }
};

// Names that never block a dish: seasoning, aromatics and water.
const SEASONING = new Set(('盐 糖 白糖 冰糖 红糖 油 食用油 植物油 花生油 菜籽油 橄榄油 香油 麻油 芝麻油 红葱油 ' +
  '酱油 生抽 老抽 醋 香醋 陈醋 料酒 黄酒 淀粉 生粉 味素 味精 鸡精 蚝油 豆瓣酱 甜面酱 番茄酱 辣椒粉 胡椒粉 ' +
  '花椒 八角 桂皮 香叶 孜然 五香粉 十三香 清水 水 温水 开水 葱 小葱 大葱 青葱 姜 姜片 蒜 蒜末 蒜瓣 香菜 ' +
  '辣椒 干辣椒 小米辣 红辣椒 青辣椒 红椒 青椒 麻酱 芝麻 白芝麻 熟芝麻 蜂蜜 柠檬汁 白胡椒 黑胡椒').split(/\s+/));
// 青椒 is a real ingredient in many dishes; keep it as a main ingredient.
SEASONING.delete('青椒');
SEASONING.delete('红椒');

const TOOL = /锅|烤箱|烤盘|烤网|铝箔|电饭煲|电炖锅|高压锅|汤匙|水果刀|菜刀|砧板|保鲜膜|厨房纸|烧烤炉|烤架|平底|炒锅|蒸锅|勺|杯|碗|盘|筷子|剪刀|温度计|秤|擀面杖|蒸笼|蒸屉|塑料盆|手套|微波炉|案板|削皮刀|擦丝器|刨丝器|锡纸|工具|原料|材料$/;
const SEASONING_PATTERNS = [
  /盐$/, /^精盐$/, /^海盐$/, /糖$/, /^冰糖$/, /^红糖$/, /^白砂糖$/, /^白糖$/,
  /^(白|黑)?胡椒/, /^花椒/, /^青花椒$/, /^孜然/, /^生抽/, /^老抽/, /^酱油$/, /^红酱油$/, /^白酱油$/, /^豉油/, /^蒸鱼豉油$/, /^蚝油$/, /^耗油$/,
  /^淀粉$/, /^生粉$/, /^土豆淀粉$/, /^玉米淀粉$/, /^料酒/, /^黄酒/, /^花雕/, /^白酒$/, /^啤酒$/, /^米酒$/,
  /^姜/, /^蒜/, /^葱/, /^香葱/, /^青葱/, /^大葱/, /^小葱$/, /^小料$/,
  /^食用油$/, /^植物油$/, /^食用植物油$/, /^猪油$/, /^黄油$/, /^香油$/, /^麻油$/, /^芝麻油$/, /^芝麻香油$/, /^花椒油$/, /^红油$/, /^油泼辣子$/, /^白醋$/, /^陈醋$/, /^香醋$/, /^黑醋$/,
  /豆瓣酱$/, /^黄豆酱$/, /^甜面酱$/, /^番茄酱$/, /^芝麻酱$/, /^腐乳$/, /^南乳$/, /^红豆腐乳$/, /^南腐乳$/, /^柱侯酱$/, /^咖喱块$/, /^卤料包$/,
  /^烧烤撒料$/, /^椒盐粉$/, /^吉士粉$/, /^五香粉$/, /^十三香$/, /^辣椒粉$/, /^花椒粉$/, /^味素$/, /^味精$/, /^鸡精$/, /^鸡粉$/,
  /^盐焗鸡粉$/, /^新奥尔良/, /^豉油调味汁$/, /^泡椒$/, /^野山椒$/, /^泡姜$/, /^小米辣$/, /^小米椒$/, /^干辣椒/, /^辣椒$/, /^红辣椒$/, /^青红辣椒$/, /^黑椒$/,
  /^肉桂皮$/, /^肉桂$/, /^豆蔻$/, /^大料$/, /^白芷$/, /^香叶$/, /^八角$/, /^桂皮$/,
  /^洋葱粉$/, /^蒜粉$/, /^姜粉$/, /^红辣椒粉$/, /^香菜粉$/, /^辣椒面$/, /^红泡椒$/, /^泡椒$/,
  /^味淋$/, /^出汁$/, /^玉米油$/, /^红油豆瓣$/, /^香料/, /^白芝麻$/, /^熟芝麻$/,
  /^高筋面粉$/, /^中筋面粉$/, /^低筋面粉$/, /^面粉$/, /^面包糠$/,
  /^干酵母$/, /^酵母$/, /^泡打粉$/, /^小苏打$/,
  /^水$/, /^清水$/, /^温水$/, /^开水$/, /^热水$/
];
// Aromatics share one canonical name so 大蒜/蒜头/蒜末 dedupe and match any form.
const CANONICAL = {
  '大蒜': '蒜', '蒜头': '蒜', '蒜仔': '蒜', '蒜瓣': '蒜', '蒜末': '蒜', '蒜粉': '蒜',
  '生姜': '姜', '姜末': '姜', '姜片': '姜', '姜丝': '姜', '泡姜': '姜',
  '小葱': '葱', '大葱': '葱', '香葱': '葱', '青葱': '葱', '葱段': '葱', '葱花': '葱', '葱白': '葱', '小葱花': '葱',
  '白砂糖': '糖', '白糖': '糖', '冰糖': '糖', '红糖': '糖',
  '西红柿': '番茄', '马铃薯': '土豆', '鸡蛋清': '鸡蛋', '鸡蛋液': '鸡蛋',
  '风干快熟面': '快熟面', '任何牌子的快熟面': '快熟面', '高筋': '高筋面粉'
};

const CN_NUMBERS = { '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10 };

function sections(text) {
  const lines = text.split(/\r?\n/);
  const result = {};
  let current = '';
  for (const line of lines) {
    const heading = line.match(/^##\s+(.+?)\s*$/);
    if (heading) { current = heading[1]; result[current] = []; continue; }
    if (current) result[current].push(line);
  }
  return result;
}

function bullets(lines) {
  return (lines || []).map(line => line.match(/^\s*[-*]\s+(.+?)\s*$/)).filter(Boolean).map(match => match[1]);
}

const SYNONYMS = {
  '番茄': ['西红柿'], '土豆': ['马铃薯'], '鸡蛋': ['蛋'], '快熟面': ['方便面', '泡面'],
  '鳜鱼': ['桂鱼'], '青椒': ['尖椒', '柿子椒'], '猪肉': ['肉馅', '肉末', '五花肉', '里脊肉', '猪里脊肉', '猪瘦肉'],
  '牛肉': ['牛腩', '肥牛'], '鸡肉': ['鸡腿', '鸡胸', '鸡翅'],
  '葱': ['小葱', '大葱', '香葱', '青葱'],
  '蒜': ['大蒜', '蒜头', '蒜末', '蒜瓣'],
  '姜': ['生姜', '姜片', '姜末']
};

function cleanLine(value) {
  let text = value
    .replace(/\*\*/g, '')
    .replace(/\*/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/[—–－].*$/, '');
  for (let i = 0; i < 3; i++) text = text.replace(/（[^）]*）|\([^)]*\)/g, '');
  return text.split(/[：:]/)[0];
}

function cleanName(value) {
  return value
    .replace(/^(泡发好的|新鲜的|冷冻的|去皮的|切好的|熟的|生的|自制的|现成的)/, '')
    .replace(/\d+(\.\d+)?\s*(g|kg|ml|l|个|根|片|瓣|颗|只|块|汤匙|勺|杯|把|节|斤|两|克|毫升|升|%)/gi, '')
    .replace(/[0-9\-~～+*]/g, '')
    .replace(/\s+/g, '')
    .replace(/[。；，,;：:]+$/, '')
    .trim();
}

function isSeasoning(name, canonical) {
  if (SEASONING.has(name) || SEASONING.has(canonical)) return true;
  return SEASONING_PATTERNS.some(pattern => pattern.test(canonical) || pattern.test(name));
}

function ingredients(raw) {
  const mains = [];
  const optional = [];
  const seasoning = [];
  for (const line of raw) {
    const isOptional = /可选|根据口味|依个人/.test(line);
    for (const part of cleanLine(line).split(/[\/、，,；;]|或者|或/)) {
      const name = cleanName(part);
      if (!name || name.length > 20) continue;
      if (/[()（）]/.test(name)) continue;
      if (TOOL.test(name)) continue;
      if (/增稠剂|添加剂|香精|色素|防腐剂/.test(name)) continue;
      if (/[\[\]]/.test(name)) continue;
      if (/^(工具|原料|材料|调料|辅料|食材)$/.test(name)) continue;
      const canonical = CANONICAL[name] || name;
      const target = isSeasoning(name, canonical) ? seasoning : isOptional ? optional : mains;
      target.push(canonical);
    }
  }
  const unique = list => [...new Set(list)];
  return { mains: unique(mains), optional: unique(optional), seasoning: unique(seasoning) };
}

function termsFor(name) {
  return [...new Set([name, ...(SYNONYMS[name] || [])])];
}

function stepsFrom(lines) {
  const steps = [];
  for (const line of lines || []) {
    const item = line.match(/^\s*(?:\d+[.、]|[-*+])\s+(.+?)\s*$/);
    if (!item) continue;
    const text = item[1].replace(/\*\*/g, '').replace(/!\[[^\]]*\]\([^)]*\)/g, '').trim();
    if (!text || text.length < 4) continue;
    if (/^如果您遵循本指南/.test(text)) continue;
    const clipped = text.length > 120 ? text.slice(0, 118) + '…' : text;
    steps.push(clipped);
    if (steps.length >= 8) break;
  }
  return steps;
}

function minutesFrom(text, fallback) {
  const digits = text.match(/(\d{1,3})\s*分钟/);
  if (digits) return Math.min(180, Math.max(5, Number(digits[1])));
  if (/半小时/.test(text)) return 30;
  const chinese = text.match(/([一二两三四五六七八九十]{1,3})\s*分钟/);
  if (chinese) {
    const value = chinese[1];
    if (value === '十') return 10;
    if (value.length === 2 && value[0] === '十') return 10 + (CN_NUMBERS[value[1]] || 0);
    if (value.length === 2 && value[1] === '十') return (CN_NUMBERS[value[0]] || 1) * 10;
    if (value.length === 3 && value[1] === '十') return (CN_NUMBERS[value[0]] || 1) * 10 + (CN_NUMBERS[value[2]] || 0);
    return CN_NUMBERS[value] || 10;
  }
  return fallback;
}

function servingsFrom(text) {
  const match = text.match(/(\d+)\s*人份/);
  if (match) return Math.max(1, Math.min(8, Number(match[1])));
  if (/一份为一人餐|一人餐/.test(text)) return 1;
  return 2;
}

function slug(rel) {
  return 'htc-' + crypto.createHash('sha1').update(rel).digest('hex').slice(0, 10);
}

const recipes = [];
const stats = { scanned: 0, skippedNoSteps: 0, skippedNoMain: 0, skippedTitle: 0, byCategory: {} };

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { walk(full); continue; }
    if (!entry.name.endsWith('.md')) continue;
    const rel = path.relative(ROOT, full).split(path.sep).join('/');
    const categoryKey = rel.split('/')[0];
    const category = CATEGORIES[categoryKey];
    if (!category) continue;
    stats.scanned++;

    const text = fs.readFileSync(full, 'utf8');
    const titleMatch = text.match(/^#\s+(.+?)\s*$/m);
    if (!titleMatch) { stats.skippedTitle++; continue; }
    const name = titleMatch[1].replace(/的做法$/, '').trim();
    if (!name || name.length > 30 || /模板|test/i.test(name)) { stats.skippedTitle++; continue; }
    if (/[酱汁饮料茶酒]$/.test(name)) { stats.skippedTitle++; continue; }

    const parts = sections(text);
    const { mains, optional, seasoning } = ingredients(bullets(parts['必备原料和工具'] || parts['必备原料'] || []));
    if (mains.length === 0) { stats.skippedNoMain++; continue; }
    const steps = stepsFrom(parts['操作']);
    if (steps.length < 2) { stats.skippedNoSteps++; continue; }

    const body = text.slice(0, 600);
    const minutes = minutesFrom(body, category.minutes);
    const servings = servingsFrom(text);
    const calories = Number((text.match(/预估卡路里[:：]\s*(\d+)/) || [])[1] || 0) || null;
    const difficulty = (text.match(/预估烹饪难度[:：]\s*(★+)/) || [])[1] || '';

    recipes.push({
      id: slug(rel),
      name,
      category: category.label,
      minutes,
      servings,
      calories,
      difficulty: difficulty.length || null,
      main: mains.slice(0, 6).map(ingredient => ({ name: ingredient, terms: termsFor(ingredient) })),
      optional: optional.slice(0, 6),
      seasoning: seasoning.slice(0, 10),
      steps,
      source: 'HowToCook',
      sourceUrl: 'https://github.com/Anduin2017/HowToCook/blob/master/dishes/' + rel
    });
    stats.byCategory[category.label] = (stats.byCategory[category.label] || 0) + 1;
  }
}

walk(ROOT);
recipes.sort((a, b) => a.category.localeCompare(b.category, 'zh') || a.name.localeCompare(b.name, 'zh'));
fs.writeFileSync(OUT, JSON.stringify(recipes, null, 1) + '\n', 'utf8');

const mainCounts = recipes.map(recipe => recipe.main.length);
const total = mainCounts.reduce((sum, value) => sum + value, 0);
console.log(JSON.stringify({
  output: path.relative(process.cwd(), OUT),
  recipes: recipes.length,
  ...stats,
  avgMain: Math.round((total / recipes.length) * 10) / 10,
  maxMain: Math.max(...mainCounts),
  distribution: mainCounts.reduce((acc, value) => ({ ...acc, [value]: (acc[value] || 0) + 1 }), {})
}, null, 2));
