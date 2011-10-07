import idiokit
from idiokit import callqueue

class Counter(object):
    def __init__(self):
        self.keys = dict()

    def get(self, key):
        return set(self.keys.get(key, ()))

    def contains(self, key, value=None):
        self.inc(key, value)
        return not self.dec(key, value)

    def inc(self, key, value=None):
        if key not in self.keys:
            self.keys[key] = dict()
        if value not in self.keys[key]:
            self.keys[key][value] = 1
            return True
        self.keys[key][value] += 1
        return False

    def dec(self, key, value=None):
        if key not in self.keys:
            return True
        if value not in self.keys[key]:
            return True
        self.keys[key][value] -= 1
        if self.keys[key][value] <= 0:
            del self.keys[key][value]
            if not self.keys[key]:
                del self.keys[key]
            return True
        return False

    def __nonzero__(self):
        return not not self.keys

    def __iter__(self):
        for key, values in self.keys.iteritems():
            yield key, set(values)

class TaskStopped(Exception):
    pass

class TaskFarm(object):
    def __init__(self, task, throw=TaskStopped()):
        self.task = task
        self.throw = throw

        self.tasks = dict()
        self.counter = Counter()

    def _key(self, *args, **keys):
        return tuple(args), frozenset(keys.items())

    def _check(self, key):
        if self.counter.contains(key):
            return
        if key not in self.tasks:
            return
        task = self.tasks.pop(key)
        task.throw(self.throw)

    @idiokit.stream
    def _inc(self, key, task):
        try:
            yield task.fork()
        finally:
            if self.counter.dec(key):
                callqueue.add(self._check, key)

    def inc(self, *args, **keys):
        key = self._key(*args, **keys)

        if self.counter.inc(key):
            self.tasks[key] = self.task(*args, **keys)
        task = self.tasks[key]

        return self._inc(key, task)

    def get(self, *args, **keys):
        key = self._key(*args, **keys)
        if key not in self.tasks:
            return None
        return self.tasks[key]
