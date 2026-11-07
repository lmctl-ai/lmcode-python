#!/usr/bin/env node
// Compile app.lms to app.dslb with the published lmscript compiler (npm @lmctl-ai/lmctl).
// run_lmcode owns compilation, so a capture "host" copies the private program file out.
// usage: node build.mjs [LMSCRIPT_BIN]   (default: lmscript on PATH)
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
const here = import.meta.dirname;
const bin = process.argv[2] ?? process.env.LMSCRIPT_BIN ?? 'lmscript';
const out = path.join(here, 'app.dslb');
if (process.argv.includes('--capture')) {
  const file = process.argv[process.argv.indexOf('--capture') + 1];
  const invocation = JSON.parse(fs.readFileSync(process.env.LMCODE_INVOCATION_FILE, 'utf8'));
  if (!invocation.dry) fs.copyFileSync(file, out);
  console.log('LMCODE_RETURN_BEGIN');
  console.log(JSON.stringify({ ok: true, result: null, ...(invocation.dry ? { dry: true } : {}) }));
  console.log('LMCODE_RETURN_END');
  process.exit(0);
}
const source = fs.readFileSync(path.join(here, 'app.lms'), 'utf8')
  .replace('schema="host.schema.json"', `schema=${JSON.stringify(path.join(here, 'host.schema.json'))}`);
const command = [process.execPath, path.join(here, 'build.mjs'), '--capture', '$DSLFILE'];
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rest-suite-'));
try {
  const script = path.join(dir, 'build.lms');
  fs.writeFileSync(script, `${source}\nr = run_lmcode(program, {command: ${JSON.stringify(command)}});\nrequire(r.ok, "capture failed");\n`);
  const r = spawnSync(bin, ['--base-dir', here, script], { stdio: 'inherit' });
  if (r.status !== 0) process.exit(r.status ?? 1);
  console.log(`wrote ${out} (${fs.statSync(out).size} bytes)`);
} finally { fs.rmSync(dir, { recursive: true, force: true }); }
