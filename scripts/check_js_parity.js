'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const root = path.resolve(__dirname, '..');
const engine = require(path.join(root, 'wordpress/catalyst-grit-demo/assets/catalyst-grit-demo.js'));
const fixtures = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/parity_cases.json'), 'utf8'));
assert.strictEqual(engine.VERSION, fs.readFileSync(path.join(root, 'VERSION'), 'utf8').trim());
for (const fixture of fixtures) {
  assert.deepStrictEqual(engine.generateRecord(fixture.input), fixture.expected, fixture.name);
}
console.log(`Browser contract parity passed (${fixtures.length} fixtures).`);
