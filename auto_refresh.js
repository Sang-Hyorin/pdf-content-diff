// SPDX-License-Identifier: AGPL-3.0-only
const fs = require('fs');

// Poll exact inputs: survives atomic rename, remote filesystems and missed watch events.
class AutoRefresh {
  constructor(files, build, {delay = 1500, interval = 1000, onError = () => {}} = {}) {
    this.files = files; this.build = build; this.delay = delay; this.onError = onError;
    this.signature = this.read(); this.readyAt = Date.now() + delay;
    this.pending = true; this.running = false; this.disposed = false; this.retries = 0;
    this.timer = setInterval(() => this.tick(), interval);
  }
  read() {
    try { return this.files.map(file => {
      const s = fs.statSync(file);
      return `${s.ino}:${s.size}:${s.mtimeMs}:${s.ctimeMs}`;
    }).join('|'); } catch (_) { return null; }
  }
  async tick() {
    if (this.disposed) return;
    const current = this.read();
    if (current !== this.signature) {
      this.signature = current; this.pending = true; this.retries = 0;
      this.readyAt = Date.now() + this.delay;
    }
    if (!current || !this.pending || this.running || Date.now() < this.readyAt) return;
    this.pending = false; this.running = true;
    try { await this.build(); this.retries = 0; }
    catch (error) {
      if (!this.disposed) {
        this.onError(error);
        if (++this.retries <= 3) { this.pending = true; this.readyAt = Date.now() + this.delay; }
      }
    } finally { this.running = false; }
  }
  dispose() { this.disposed = true; clearInterval(this.timer); }
}
module.exports = {AutoRefresh};
