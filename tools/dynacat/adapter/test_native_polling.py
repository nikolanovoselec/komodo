"""Characterize Dynacat's real native poller; no dashboard-specific polling loop.

Run with DYNACAT_SOURCE=/path/to/dynacat when the sibling checkout is absent.
The test needs Node, but no browser or npm dependencies.
"""
import os
from pathlib import Path
import shutil
import subprocess
import unittest


class NativePolling(unittest.TestCase):
    def test_one_second_visibility_pause_single_flight_and_resume(self):
        source = Path(os.environ.get('DYNACAT_SOURCE',
                      str(Path(__file__).resolve().parents[4] / 'dynacat')))
        script = source / 'internal/dynacat/static/js/page.js'
        if not script.exists() or not shutil.which('node'):
            self.skipTest('Requires Dynacat source checkout and Node')
        harness = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function clearWidgetPollingTimeout(');
const end = source.indexOf('function setupWidgetPolling()', start);
assert(start >= 0 && end > start, 'Native widget poller must be present');
let clock = 0, calls = 0, serial = 0, resolveFetch;
const timers = new Map();
const context = {
  document: {hidden: false}, widgetPollingStates: new Map(),
  nowMs: () => clock,
  remainingDelayMs: (interval, last) => Math.max(0, interval - (clock - last)),
  setTimeout: (fn, delay) => {const id = ++serial; timers.set(id, {fn, delay}); return id;},
  clearTimeout: id => timers.delete(id),
  updateWidget: () => {calls++; return new Promise(resolve => {resolveFetch = resolve;});},
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
(async () => {
  const widget = {isConnected: true};
  context.registerWidgetPolling(widget, 1000);
  const state = context.widgetPollingStates.get(widget);
  assert.equal(timers.get(state.timeoutId).delay, 1000);
  context.document.hidden = true;
  context.handleWidgetPollingVisibilityChange();
  assert.equal(timers.size, 0, 'Hidden documents cancel scheduled refresh');
  await context.pollWidget(state);
  assert.equal(calls, 0, 'Hidden documents do not fetch');
  clock = 5000;
  context.document.hidden = false;
  context.handleWidgetPollingVisibilityChange();
  assert.equal(timers.get(state.timeoutId).delay, 0, 'Expired widgets resume immediately');
  context.clearWidgetPollingTimeout(state);
  const pending = context.pollWidget(state);
  await context.pollWidget(state);
  assert.equal(calls, 1, 'Slow refresh cannot overlap another refresh');
  assert.equal(state.isFetching, true);
  context.document.hidden = true;
  resolveFetch();
  await pending;
  assert.equal(timers.size, 0, 'Finishing while hidden does not restart polling');
  assert.equal(state.isFetching, false);
  clock = 6000;
  context.document.hidden = false;
  const next = context.pollWidget(state);
  resolveFetch();
  await next;
  assert.equal(calls, 2);
  assert.equal(timers.get(state.timeoutId).delay, 1000, 'Next refresh waits 1 second after completion');
  widget.isConnected = false;
  await context.pollWidget(state);
  assert.equal(context.widgetPollingStates.size, 0, 'Removed widgets stop polling');
  assert.equal(timers.size, 0);
  console.log('Native Dynacat poller: 1s, hidden pause, no overlap, resume and teardown PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
        result = subprocess.run(['node', '-e', harness, str(script)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
