'use strict';
// Resolve the sibling Deobfuscator-Luraph-V15 repo relative to this file (or via
// FLOWAUTH_REPO), instead of a machine-specific absolute path.
const fs = require('fs');
const path = require('path');
const HERE = __dirname;

function findRepo() {
  const names = ['Deobfuscator-Luraph-V15', 'deobfuscator-luraph-v15'];
  const bases = [process.env.FLOWAUTH_REPO, path.dirname(HERE), require('os').homedir()]
    .filter(Boolean);
  for (const base of bases) {
    if (process.env.FLOWAUTH_REPO && base === process.env.FLOWAUTH_REPO &&
        fs.existsSync(path.join(base, 'src', 'vmmap.js'))) return base;
    for (const name of names) {
      const cand = path.join(base, name);
      if (fs.existsSync(path.join(cand, 'src', 'vmmap.js'))) return cand;
    }
  }
  throw new Error('Deobfuscator-Luraph-V15 repo not found (set FLOWAUTH_REPO).');
}

const MAIN = findRepo();
const vmmap = require(path.join(MAIN, 'src', 'vmmap'));
const WORK = path.join(HERE, 'flowauth_crack', 'work');
const srcPath = path.join(WORK, 'payload_devirt.lua');
const src = fs.readFileSync(srcPath, 'latin1');
const patched = vmmap.patchEntries(src, srcPath, 'payload');
fs.writeFileSync(path.join(WORK, 'payload_patched.luau'), patched, 'latin1');
const i = patched.indexOf('__PF[C]');
console.log('C-hook region:', JSON.stringify(patched.slice(i, i + 200)));
const j = patched.indexOf('__PF[o]');
console.log('o-hook region:', JSON.stringify(patched.slice(j, j + 120)));
console.log('patched len:', patched.length);
