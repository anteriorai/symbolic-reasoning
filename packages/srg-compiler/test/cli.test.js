/**
 * Tests for the srg-compile CLI
 */

import { after, describe, it } from 'node:test';
import assert from 'node:assert';
import { spawnSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const CLI = fileURLToPath(new URL('../dist/cli.js', import.meta.url));
const SOURCE = 'predicate a: "A?"\noutcome y: "Y"\npath p: a => y\n';

const dirs = [];
after(() => dirs.forEach(dir => fs.rmSync(dir, { recursive: true, force: true })));

function compileIn(fileName, ...args) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'srg-cli-'));
  dirs.push(dir);
  const input = path.join(dir, fileName);
  fs.writeFileSync(input, SOURCE);
  const result = spawnSync(process.execPath, [CLI, input, ...args], { cwd: dir, encoding: 'utf8' });
  return { dir, input, result };
}

describe('srg-compile', () => {
  it('writes <input>.json next to a .srg input', () => {
    const { input, result } = compileIn('policy.srg');
    assert.strictEqual(result.status, 0, result.stderr);
    assert.strictEqual(fs.readFileSync(input, 'utf8'), SOURCE);
    assert.ok(JSON.parse(fs.readFileSync(`${input}.json`, 'utf8')).predicates.a);
  });

  for (const fileName of ['policy.txt', 'policy.SRG', 'policy']) {
    it(`keeps the source of ${fileName} and writes ${fileName}.json`, () => {
      const { input, result } = compileIn(fileName);
      assert.strictEqual(result.status, 0, result.stderr);
      assert.strictEqual(fs.readFileSync(input, 'utf8'), SOURCE);
      assert.ok(JSON.parse(fs.readFileSync(`${input}.json`, 'utf8')).predicates.a);
    });
  }

  it('refuses an --output that names the input file', () => {
    const { dir, input, result } = compileIn('policy.srg', '--output', './policy.srg');
    assert.strictEqual(result.status, 1);
    assert.match(result.stderr, /Output path is the input file/);
    assert.strictEqual(fs.readFileSync(input, 'utf8'), SOURCE);
    assert.deepStrictEqual(fs.readdirSync(dir), ['policy.srg']);
  });

  it('refuses an --output that is a symlink to the input file', () => {
    const { dir, input } = compileIn('policy.srg');
    const link = path.join(dir, 'out.json');
    fs.symlinkSync(input, link);
    const result = spawnSync(process.execPath, [CLI, input, '-o', link], { encoding: 'utf8' });
    assert.strictEqual(result.status, 1);
    assert.match(result.stderr, /Output path is the input file/);
    assert.strictEqual(fs.readFileSync(input, 'utf8'), SOURCE);
  });
});
