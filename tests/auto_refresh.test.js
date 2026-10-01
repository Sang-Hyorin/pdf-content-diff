const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {AutoRefresh} = require('../auto_refresh');

test('debounces writes, survives replacement, serializes builds and disposes', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pdf-refresh-'));
  const file = path.join(dir, 'new.pdf'); fs.writeFileSync(file, 'initial');
  let builds = 0, release;
  const watcher = new AutoRefresh([file], async () => {
    builds++;
    if (builds === 2) await new Promise(resolve => release = resolve);
  }, {delay: 100000, interval: 100000});
  const flush = async () => { watcher.readyAt = 0; await watcher.tick(); };
  try {
    await flush(); assert.equal(builds, 1);
    fs.writeFileSync(file, 'part'); await watcher.tick(); assert.equal(builds, 1);
    fs.writeFileSync(file, 'complete'); await watcher.tick(); assert.equal(builds, 1);
    const pending = flush(); assert.equal(builds, 2);
    fs.unlinkSync(file); await watcher.tick();
    fs.writeFileSync(file, 'replacement'); await watcher.tick();
    await flush(); assert.equal(builds, 2);
    release(); await pending; await flush(); assert.equal(builds, 3);
    watcher.dispose(); fs.writeFileSync(file, 'ignored'); await flush(); assert.equal(builds, 3);
  } finally { watcher.dispose(); fs.rmSync(dir, {recursive:true}); }
});

test('retries a transient failure without simultaneous builds', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pdf-refresh-'));
  const file = path.join(dir, 'new.pdf'); fs.writeFileSync(file, 'test');
  let calls = 0, errors = 0;
  const watcher = new AutoRefresh([file], async () => {
    if (++calls === 1) throw new Error('incomplete PDF');
  }, {delay:100000, interval:100000, onError:() => errors++});
  try {
    watcher.readyAt = 0; await watcher.tick();
    assert.equal(errors, 1); assert.equal(watcher.pending, true);
    watcher.readyAt = 0; await watcher.tick(); assert.equal(calls, 2);
    assert.equal(watcher.pending, false);
  } finally { watcher.dispose(); fs.rmSync(dir, {recursive:true}); }
});
