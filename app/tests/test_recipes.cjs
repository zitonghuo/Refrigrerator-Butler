const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const recipes = require('../cloudfunctions/fridgeApi/recipes.json');
const { matchRecipes } = require('../cloudfunctions/fridgeApi/insights');

const NOW = Date.parse('2026-10-27T02:00:00Z');
const items = list => list.map(([name, expiry = '']) => ({ id: name, name, quantity: 1, unit: '个', location: '冷藏', expiry }));

test('expired batches never satisfy a recipe', () => {
  const result = matchRecipes(recipes, items([['番茄', '2026-10-19'], ['鸡蛋', '']]), { now: NOW });
  const dish = result.recipes.find(x => x.name === '西红柿炒鸡蛋');
  assert.ok(dish);
  assert.deepEqual(dish.missing, ['番茄']);
  assert.equal(dish.matched.length, 1);
});

test('exclude removes recipes that need a disliked ingredient', () => {
  const result = matchRecipes(recipes, items([['番茄'], ['鸡蛋']]), { now: NOW, exclude: ['鸡蛋'] });
  assert.equal(result.recipes.some(x => x.name === '西红柿炒鸡蛋'), false);
  assert.equal(result.recipes.some(x => x.matched.some(m => m.name === '鸡蛋')), false);
});

test('results are grouped by missing count and keep the source', () => {
  const result = matchRecipes(recipes, items([['番茄'], ['鸡蛋']]), { now: NOW });
  assert.ok(result.ready.length > 0);
  assert.equal(result.ready.every(x => x.missing.length === 0), true);
  assert.equal(result.almost.every(x => x.missing.length === 1), true);
  assert.ok(result.inspiration.length <= 20);
  assert.ok(result.recipes.length > 100);
  assert.equal(result.recipes[0].missing.length, 0);
  for (const recipe of result.recipes) {
    assert.equal(recipe.source, 'HowToCook');
    assert.match(recipe.sourceUrl, /^https:\/\/github\.com\/Anduin2017\/HowToCook\//);
    assert.ok(recipe.steps.length >= 2);
  }
});

test('empty inventory yields no ready dishes but still lists real recipes', () => {
  const result = matchRecipes(recipes, [], { now: NOW });
  assert.equal(result.ready.length, 0);
  assert.equal(result.recipes.length, recipes.length);
  assert.ok(result.inspiration.length <= 20);
  assert.ok(result.recipes.every(x => x.missing.length > 0));
});
