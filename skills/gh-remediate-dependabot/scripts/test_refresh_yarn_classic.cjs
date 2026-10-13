'use strict';
// Run with REMEDIATION_TOOLS pointing to the disposable parser/semver tools directory.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');
const tools = process.env.REMEDIATION_TOOLS;
if (!tools) throw new Error('Set REMEDIATION_TOOLS to the disposable tools directory.');
const lockfile = createRequire(path.join(tools, 'package.json'))('@yarnpkg/lockfile');
const script = path.join(__dirname, 'refresh_yarn_classic.cjs');

function fixture(t, { manifest = {}, extra = {}, mode = 'valid' } = {}) {
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), 'yarn-refresh-test-'));
  t.after(() => fs.rmSync(repo, { recursive: true, force: true }));
  const graph = {
    'parent@1.0.0': { version: '1.0.0', dependencies: { child: '^1.0.0', '@scope/child': '^2.0.0' } },
    'child@^1.0.0': { version: '1.0.0', resolved: 'https://example.test/child.tgz', integrity: 'old' },
    '@scope/child@^2.0.0': { version: '2.0.0', integrity: 'old' },
    'childish@^1.0.0': { version: '1.0.0' },
    ...extra,
  };
  fs.writeFileSync(path.join(repo, 'package.json'), JSON.stringify({ packageManager: 'yarn@1.22.22', dependencies: { parent: '1.0.0' }, ...manifest }));
  fs.writeFileSync(path.join(repo, 'yarn.lock'), lockfile.stringify(graph));
  const yarn = path.join(repo, 'fake-yarn.cjs');
  fs.writeFileSync(yarn, `
    const fs = require('node:fs');
    const lockfile = require(${JSON.stringify(require.resolve('@yarnpkg/lockfile', { paths: [tools] }))});
    if (process.argv.includes('--version')) { console.log('1.22.22'); process.exit(0); }
    const graph = lockfile.parse(fs.readFileSync('yarn.lock', 'utf8')).object;
    if (graph['child@^1.0.0']) throw new Error('Selected cache was not invalidated');
    if (!graph['childish@^1.0.0']) throw new Error('Wrong package cache invalidated');
    if (${JSON.stringify(mode)} === 'failure') process.exit(2);
    graph['child@^1.0.0'] = { version: ${JSON.stringify(mode === 'unexpected' ? '1.0.9' : '1.0.1')}, integrity: 'generated', dependencies: { leaf: '^1.0.0' } };
    graph['leaf@^1.0.0'] = { version: '1.0.0', integrity: 'generated' };
    if (!graph['@scope/child@^2.0.0']) graph['@scope/child@^2.0.0'] = { version: '2.0.1', integrity: 'generated' };
    if (${JSON.stringify(mode)} === 'churn') graph['parent@1.0.0'].version = '1.0.2';
    if (${JSON.stringify(mode)} === 'addition') graph['unrelated@^1.0.0'] = { version: '1.0.0' };
    if (${JSON.stringify(mode)} === 'manifest') fs.writeFileSync('package.json', '{}');
    fs.writeFileSync('yarn.lock', lockfile.stringify(graph));
  `);
  const original = fs.readFileSync(path.join(repo, 'yarn.lock'), 'utf8');
  const originalManifest = fs.readFileSync(path.join(repo, 'package.json'), 'utf8');
  const run = (...args) => spawnSync(process.execPath, [script, '--repo', repo, '--tools', tools, '--target', 'child@1.0.1', ...args], { encoding: 'utf8' });
  return { repo, yarn, original, originalManifest, run };
}
test('read-only plan leaves files byte-identical', t => {
  const f = fixture(t); const r = f.run();
  assert.equal(r.status, 0, r.stderr);
  assert.equal(fs.readFileSync(path.join(f.repo, 'yarn.lock'), 'utf8'), f.original);
});
test('regenerates selected scoped/unscoped packages and permits required children; repeat is a no-op', t => {
  const f = fixture(t);
  const r = f.run('--target', '@scope/child@2.0.1', '--apply', '--yarn-cli', f.yarn);
  assert.equal(r.status, 0, r.stderr);
  const after = fs.readFileSync(path.join(f.repo, 'yarn.lock'), 'utf8');
  const graph = lockfile.parse(after).object;
  assert.equal(graph['child@^1.0.0'].version, '1.0.1');
  assert.equal(graph['@scope/child@^2.0.0'].version, '2.0.1');
  assert.deepEqual(graph['parent@1.0.0'], lockfile.parse(f.original).object['parent@1.0.0']);
  assert.equal(f.run('--target', '@scope/child@2.0.1', '--check').status, 0);
  assert.equal(f.run('--target', '@scope/child@2.0.1', '--apply').status, 0);
  assert.equal(fs.readFileSync(path.join(f.repo, 'yarn.lock'), 'utf8'), after);
});
for (const mode of ['unexpected', 'churn', 'addition', 'failure', 'manifest']) {
  test(`restores original files on ${mode}`, t => {
    const f = fixture(t, { mode });
    const r = f.run('--apply', '--yarn-cli', f.yarn);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /restored/);
    assert.equal(fs.readFileSync(path.join(f.repo, 'yarn.lock'), 'utf8'), f.original);
    assert.equal(fs.readFileSync(path.join(f.repo, 'package.json'), 'utf8'), f.originalManifest);
  });
}
test('rejects a target excluded by an exact parent range before writes', t => {
  const f = fixture(t, { extra: { 'child@1.0.0': { version: '1.0.0' } } });
  const r = f.run('--apply', '--yarn-cli', f.yarn);
  assert.equal(r.status, 1); assert.match(r.stderr, /allowed by child@1.0.0/);
  assert.equal(fs.readFileSync(path.join(f.repo, 'yarn.lock'), 'utf8'), f.original);
});
test('requires a reviewed target for every installed major line', t => {
  const f = fixture(t, { extra: { 'child@^2.0.0': { version: '2.0.0' } } });
  assert.equal(f.run().status, 1);
  assert.equal(f.run('--target', 'child@2.0.1').status, 0);
});
for (const manifest of [{ workspaces: ['packages/*'] }, { dependencies: { child: '^1.0.0' } }, { resolutions: { '**/child': '1.0.0' } }]) {
  test(`rejects unsupported graph ${JSON.stringify(manifest)}`, t => {
    const f = fixture(t, { manifest });
    assert.equal(f.run('--apply', '--yarn-cli', f.yarn).status, 1);
    assert.equal(fs.readFileSync(path.join(f.repo, 'yarn.lock'), 'utf8'), f.original);
  });
}
test('rejects hidden aliased occurrences even when the regular occurrence is already patched', t => {
  const f = fixture(t, { extra: { 'child@^1.0.0': { version: '1.0.1' }, 'shortcut@npm:child@^1.0.0': { version: '1.0.0' } } });
  const r = f.run('--check');
  assert.equal(r.status, 1); assert.match(r.stderr, /Alias occurrence/);
  assert.equal(fs.readFileSync(path.join(f.repo, 'yarn.lock'), 'utf8'), f.original);
});
test('unrelated similarly named resolutions do not block a target', t => {
  const f = fixture(t, { manifest: { resolutions: { '**/childish': '1.0.0' } } });
  assert.equal(f.run().status, 0);
});
test('rejects wildcard package resolutions conservatively', t => {
  const f = fixture(t, { manifest: { resolutions: { '**/*': '1.0.0' } } });
  const r = f.run(); assert.equal(r.status, 1); assert.match(r.stderr, /Wildcard package resolution/);
});
