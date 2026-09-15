"""Lifecycle-owned cache warmers; each source cache retains its TTL/singleflight.

Callbacks must be nonblocking cache kickoff hooks, not raw upstream collectors.
A fixed worker per hook isolates failures without queues or unbounded spawning.
No thread starts on import/construction. Existing upstream flights may finish
on close; stopping the sampler prevents any subsequent background kickoff.
"""
import threading
import time


class Sampler:
    def __init__(self, callbacks, interval=.25):
        self.callbacks = tuple(callbacks)
        self.interval = interval
        self.halt = threading.Event()
        self.threads = []

    def start(self):
        if self.threads or self.halt.is_set():
            return
        for index, callback in enumerate(self.callbacks):
            thread = threading.Thread(target=self._run, args=(callback,),
                                      daemon=True, name=f'telemetry-{index}')
            self.threads.append(thread)
            thread.start()

    def _run(self, callback):
        while not self.halt.is_set():
            try:
                callback()
            except Exception:
                # Source caches own health reporting. Never log upstream secrets.
                pass
            self.halt.wait(self.interval)

    def stop(self, timeout=1):
        self.halt.set()
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(max(0, deadline - time.monotonic()))
