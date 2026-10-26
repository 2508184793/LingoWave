"""Bounded queues that coalesce revisions of the same spoken sentence."""
from __future__ import annotations

import queue
import threading
import time
from collections import OrderedDict


class RevisionQueue:
    def __init__(self, capacity=2):
        self.capacity = capacity
        self.pending = OrderedDict()
        self.condition = threading.Condition()

    def put(self, item):
        with self.condition:
            previous = self.pending.get(item.id)
            if previous and (previous.final or previous.revision > item.revision):
                return None
            self.pending[item.id] = item
            dropped = None
            if len(self.pending) > self.capacity:
                _, dropped = self.pending.popitem(last=False)
            self.condition.notify()
            return dropped

    def get(self, timeout=0.2):
        deadline = time.monotonic() + timeout
        with self.condition:
            while not self.pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                self.condition.wait(remaining)
            return self.pending.popitem(last=False)[1]


class Superseded:
    """Event-compatible cancellation for a stopped session or an obsolete draft."""
    def __init__(self, session_stop, obsolete):
        self.session_stop, self.obsolete = session_stop, obsolete

    def is_set(self):
        return self.session_stop.is_set() or self.obsolete()
