#!/usr/bin/env node
'use strict';

// Invalidate selected cached resolutions; Yarn generates every replacement entry.
// Based on Dependabot's yarn/subdependency-updater.ts, with stricter local checks.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');
const { isDeepStrictEqual } = require('node:util');

function fail(message) { throw new Error(message); }
function splitSelector(selector) {
  const match = /^(@[^@]+|[^@]+)@(.+)$/.exec(selector);
  if (!match) fail(`Unsupported selector: ${selector}`);
  return { name: match[1], range: match[2] };
}
function options(args) {
  const result = { targets: [], apply: false, check: false, includeDirect: false };
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    if (key === '--apply' || key === '--check') result[key.slice(2)] = true;
    else if (key === '--include-direct') result.includeDirect = true;
    else if (['--repo', '--tools', '--yarn-cli', '--registry', '--target'].includes(key)) {
      const value = args[++i];
      if (!value || value.startsWith('--')) fail(`Missing value for ${key}`);
      if (key === '--target') result.targets.push(value);
      else result[key.slice(2)] = value;
    } else fail(`Unknown argument: ${key}`);
  }
  if (!result.repo || !result.tools || !result.targets.length || (result.apply && result.check)) {
    fail('Usage: --repo PATH --tools TOOLS_DIRECTORY --target PACKAGE@VERSION [--target ...] [--include-direct] [--apply --yarn-cli PATH --registry URL | --check]. Default: read-only plan.');
  }
  return result;
}
function main(args) {
  const opts = options(args);
  const toolRequire = createRequire(path.join(path.resolve(opts.tools), 'package.json'));
  const lockfile = toolRequire('@yarnpkg/lockfile');
  const semver = toolRequire('semver');
  const repo = fs.realpathSync(opts.repo);
  const manifestPath = path.join(repo, 'package.json');
  const lockPath = path.join(repo, 'yarn.lock');
  const originalManifest = fs.readFileSync(manifestPath, 'utf8');
  const manifest = JSON.parse(originalManifest);
  if (manifest.workspaces) fail('Workspace graph: use a workspace-aware updater; this helper supports one manifest only.');
  if (manifest.packageManager && !/^yarn@1\./.test(manifest.packageManager)) fail('This helper requires Yarn Classic.');
  const originalLock = fs.readFileSync(lockPath, 'utf8');
  if (!/^# yarn lockfile v1\r?$/m.test(originalLock)) fail('Expected a Yarn Classic v1 lockfile.');
  function parse(content) {
    const parsed = lockfile.parse(content);
    if (parsed.type !== 'success') fail(`Lockfile parse failed: ${parsed.type}`);
    return parsed.object;
  }
  const before = parse(originalLock);
  const targets = new Map();
  let hasDirectTarget = false;
  for (const value of opts.targets) {
    const { name, range: version } = splitSelector(value);
    if (!semver.valid(version) || semver.prerelease(version)) fail(`Expected a stable exact version: ${value}`);
    const values = targets.get(name) || [];
    if (!values.includes(version)) values.push(version);
    targets.set(name, values);
    const directRanges = ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']
      .map(section => manifest[section] || {})
      .filter(section => Object.hasOwn(section, name))
      .map(section => section[name]);
    if (directRanges.length) {
      hasDirectTarget = true;
      if (!opts.includeDirect) fail(`Direct dependency ${name}: use the normal Yarn upgrade workflow, or pass --include-direct to refresh every direct and transitive lockfile occurrence after reviewing the direct range.`);
      for (const range of directRanges) {
        if (!semver.validRange(range) || !values.some(version => semver.satisfies(version, range))) {
          fail(`No reviewed target for ${name} satisfies direct manifest range ${range}.`);
        }
      }
    }
  }
  if (opts.includeDirect && !hasDirectTarget) fail('--include-direct requires at least one selected package that is a direct manifest dependency.');
  // Aliased occurrences must not silently escape the all-occurrences check.
  for (const selector of Object.keys(before)) {
    const { range } = splitSelector(selector);
    const alias = /^npm:(@[^@]+|[^@]+)(?:@.*)?$/.exec(range);
    if (alias && targets.has(alias[1])) fail(`Alias occurrence of selected package: ${selector}. Use an alias-aware updater.`);
  }
  // Parent-path globs are fine; wildcard package names need an aware updater.
  for (const key of Object.keys(manifest.resolutions || {})) {
    const parts = key.split('/');
    const resolutionName = parts.length > 1 && parts[parts.length - 2].startsWith('@') ? parts.slice(-2).join('/') : parts[parts.length - 1];
    if (/[?*\[\]{}()!+]/.test(resolutionName)) fail(`Wildcard package resolution ${key}: investigate its effect before using this helper.`);
    for (const name of targets.keys()) {
      if (resolutionName === name) fail(`Existing resolution ${key} affects ${name}; investigate its parent contract first.`);
    }
  }
  function targetFor(selector, entry) {
    const { name, range } = splitSelector(selector);
    const versions = targets.get(name);
    if (!versions) return undefined;
    if (!semver.valid(entry.version) || !semver.validRange(range)) fail(`Unsupported dependency source/range: ${selector}`);
    const candidates = versions.filter(version =>
      semver.satisfies(version, range) && semver.major(version) === semver.major(entry.version) &&
      (semver.major(version) !== 0 || semver.minor(version) === semver.minor(entry.version)));
    if (candidates.length !== 1) fail(`Need exactly one reviewed, same-release-line target allowed by ${selector} (locked ${entry.version}).`);
    if (semver.gt(entry.version, candidates[0])) fail(`Target would downgrade ${selector}: ${entry.version} -> ${candidates[0]}`);
    return candidates[0];
  }
  const plan = [];
  for (const [selector, entry] of Object.entries(before)) {
    const target = targetFor(selector, entry);
    if (target) plan.push({ selector, before: entry.version, target });
  }
  for (const name of targets.keys()) {
    if (!plan.some(row => splitSelector(row.selector).name === name)) fail(`Package not found in lockfile: ${name}`);
  }
  function checkTargets(graph) {
    for (const { selector, target } of plan) {
      if (!graph[selector] || graph[selector].version !== target) fail(`Resolver did not select reviewed target ${selector} -> ${target}`);
    }
    for (const [selector, entry] of Object.entries(graph)) {
      const { name, range } = splitSelector(selector);
      if (targets.has(name) && (!targets.get(name).includes(entry.version) || !semver.satisfies(entry.version, range))) {
        fail(`Unreviewed or incompatible target occurrence: ${selector} -> ${entry.version}`);
      }
    }
  }
  console.log(JSON.stringify({ repository: repo, mode: opts.check ? 'check' : opts.apply ? 'apply' : 'plan', resolutions: plan }, null, 2));
  if (opts.check) { checkTargets(before); return; }
  if (!opts.apply || plan.every(row => row.before === row.target)) return;
  if (!opts['yarn-cli']) fail('--apply requires the repository-supported Yarn CLI JavaScript path.');
  const yarnCli = fs.realpathSync(opts['yarn-cli']);
  const version = spawnSync(process.execPath, [yarnCli, '--version'], { cwd: repo, encoding: 'utf8' });
  if (version.status !== 0 || !/^1\.\d+\.\d+\s*$/.test(version.stdout)) fail('The selected CLI is not Yarn Classic.');
  const installArgs = [yarnCli, 'install', '--non-interactive', '--ignore-scripts'];
  if (opts.registry) {
    const registry = new URL(opts.registry);
    if (registry.protocol !== 'https:' || registry.username || registry.password) fail('Use an approved HTTPS registry URL without embedded credentials.');
    installArgs.push('--registry', opts.registry);
  }
  const backup = fs.mkdtempSync(path.join(os.tmpdir(), 'yarn-classic-refresh-'));
  fs.writeFileSync(path.join(backup, 'yarn.lock'), originalLock);
  fs.writeFileSync(path.join(backup, 'package.json'), originalManifest);
  console.log(`Original files backed up in ${backup}`);
  try {
    const unlocked = { ...before };
    for (const row of plan) if (row.before !== row.target) delete unlocked[row.selector];
    fs.writeFileSync(lockPath, lockfile.stringify(unlocked));
    const installed = spawnSync(process.execPath, installArgs, { cwd: repo, stdio: 'inherit' });
    if (installed.status !== 0) fail(`Yarn regeneration failed (${installed.status ?? installed.signal}).`);
    if (fs.readFileSync(manifestPath, 'utf8') !== originalManifest) fail('Yarn changed package.json unexpectedly.');
    const after = parse(fs.readFileSync(lockPath, 'utf8'));
    checkTargets(after);
    for (const [selector, entry] of Object.entries(before)) {
      if (!targets.has(splitSelector(selector).name) && !isDeepStrictEqual(entry, after[selector])) {
        fail(`Unrelated existing lockfile entry changed: ${selector}`);
      }
    }
    // New child selectors must be reachable from a selected package's new graph.
    const reachable = new Set();
    function visit(selector) {
      if (reachable.has(selector)) return;
      reachable.add(selector);
      const entry = after[selector];
      if (!entry) fail(`Missing dependency selector: ${selector}`);
      for (const [name, range] of Object.entries({ ...entry.dependencies, ...entry.optionalDependencies })) {
        const child = `${name}@${range}`;
        if (!after[child] && Object.hasOwn(manifest.resolutions || {}, name)) continue;
        visit(child);
      }
    }
    for (const row of plan) visit(row.selector);
    const additions = Object.keys(after).filter(selector => !Object.hasOwn(before, selector));
    for (const selector of additions) if (!reachable.has(selector)) fail(`Unrelated new lockfile entry: ${selector}`);
    console.log(JSON.stringify({ result: 'regenerated', requiredNewSelectors: additions, next: 'Run frozen install with lifecycle scripts, inspect installed paths, audit, and application tests.' }, null, 2));
  } catch (error) {
    fs.writeFileSync(lockPath, originalLock);
    fs.writeFileSync(manifestPath, originalManifest);
    console.error(`Original manifest and lockfile restored. node_modules may have changed; restore it with a frozen install. Backup: ${backup}`);
    throw error;
  }
}
if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { main, splitSelector };
