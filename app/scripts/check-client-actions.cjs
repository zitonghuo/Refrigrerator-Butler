#!/usr/bin/env node
'use strict';
// Every action the mini program calls must exist in the cloud function.
// media.* is routed by media.js, so it is checked separately.
const fs = require('node:fs');
const path = require('node:path');
const { ACTIONS } = require(path.join(__dirname, '..', 'cloudfunctions', 'fridgeApi', 'service'));

const MINI = path.join(__dirname, '..', 'miniprogram');
const used = new Set();

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { if (entry.name !== 'node_modules') walk(full); continue; }
    if (!entry.name.endsWith('.js')) continue;
    const source = fs.readFileSync(full, 'utf8');
    for (const match of source.matchAll(/api\.(?:call|write)\(\s*['"]([a-zA-Z.]+)['"]/g)) used.add(match[1]);
  }
}

walk(MINI);
const missing = [...used].filter(action => !action.startsWith('media.') && !require('../cloudfunctions/fridgeApi/glm-vision').ACTIONS.has(action) && !ACTIONS.has(action));
const unused = [...ACTIONS].filter(action => !used.has(action)).sort();

console.log(JSON.stringify({
  clientActions: used.size,
  cloudActions: ACTIONS.size,
  missing,
  unusedActions: unused
}, null, 2));

if (missing.length) {
  console.error('Missing backend actions: ' + missing.join(', '));
  process.exitCode = 1;
} else {
  console.log('PASS: every non-media client action exists in fridgeApi');
}
