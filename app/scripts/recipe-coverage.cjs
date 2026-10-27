#!/usr/bin/env node
'use strict';
// Measures how well the recipe corpus covers typical fridge baskets.
// Usage: node scripts/recipe-coverage.cjs
const path = require('node:path');
const recipes = require(path.join(__dirname, '..', 'cloudfunctions', 'fridgeApi', 'recipes.json'));
const { matchRecipes } = require(path.join(__dirname, '..', 'cloudfunctions', 'fridgeApi', 'insights'));

const NOW = Date.parse('2026-10-27T02:00:00Z');
const BASKETS = [
  ['番茄', '鸡蛋', '葱'],
  ['土豆', '青椒', '猪肉'],
  ['西兰花', '鸡胸肉'],
  ['黄瓜', '蒜'],
  ['豆腐', '葱'],
  ['牛肉', '洋葱', '土豆', '胡萝卜'],
  ['排骨', '姜'],
  ['鱼', '葱', '姜'],
  ['鸡蛋', '牛奶', '面包'],
  ['米饭', '鸡蛋', '火腿'],
  ['白菜', '豆腐', '粉条'],
  ['茄子', '青椒', '蒜'],
  ['虾', '葱', '姜'],
  ['面条', '青菜', '鸡蛋'],
  ['蘑菇', '青菜'],
  ['鸡翅', '可乐'],
  ['豆角', '猪肉'],
  ['冬瓜', '排骨'],
  ['韭菜', '鸡蛋'],
  ['羊肉', '胡萝卜']
];

const rows = BASKETS.map(names => {
  const items = names.map(name => ({ id: name, name, quantity: 1, unit: '个', location: '冷藏', expiry: '' }));
  const result = matchRecipes(recipes, items, { now: NOW });
  const best = result.recipes[0] || null;
  return {
    basket: names.join(' + '),
    ready: result.ready.length,
    almost: result.almost.length,
    bestMissing: best ? best.missing.length : null,
    best: best ? best.name : '（无匹配）'
  };
});

const ready = rows.filter(row => row.ready > 0).length;
const almost = rows.filter(row => row.ready === 0 && row.almost > 0).length;
const none = rows.length - ready - almost;
const missingValues = rows.map(row => row.bestMissing).filter(value => value !== null);
const averageMissing = missingValues.length ? missingValues.reduce((sum, value) => sum + value, 0) / missingValues.length : null;

console.log('basket'.padEnd(34) + 'ready  almost  best-missing  best dish');
for (const row of rows) {
  console.log(row.basket.padEnd(34) + String(row.ready).padStart(5) + String(row.almost).padStart(8) +
    String(row.bestMissing).padStart(14) + '  ' + row.best);
}
console.log('');
console.log(JSON.stringify({
  baskets: rows.length,
  withReady: ready,
  withAlmostOnly: almost,
  noMatch: none,
  averageMissingToBest: averageMissing === null ? null : Math.round(averageMissing * 100) / 100,
  recipes: recipes.length
}, null, 2));
