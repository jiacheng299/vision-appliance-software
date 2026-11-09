"""Bounded background writer for local safety observations."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread


class _AuditFile(RotatingFileHandler):
    def handleError(self, record):
        raise  # Stop the writer on the first I/O failure.


class SafetyAudit:
    def __init__(self, path: Path, *, queue_size: int = 128):
        self._pending = Queue(maxsize=queue_size)
        self._stopped = Event()
        self._discard_pending = Event()
        self._drop_lock = Lock()
        self._dropped = 0
        self._worker = Thread(target=self._write, args=(path,), daemon=True, name='model-safety-audit')
        self._worker.start()

    @property
    def accepting(self) -> bool:
        return self._worker.is_alive() and not self._stopped.is_set()

    def submit(self, record: dict):
        if self._stopped.is_set():
            return
        try:
            self._pending.put_nowait(record)
        except Full:
            with self._drop_lock:
                self._dropped += 1

    def close(self):
        self._stopped.set()
        self._worker.join(timeout=.5)
        # A stalled write may finish later, but the old writer must stop draining its queue.
        self._discard_pending.set()

    def _write(self, path):
        handler = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = _AuditFile(path, maxBytes=5 * 1024 * 1024, backupCount=2, encoding='utf-8', delay=True)
            while not self._discard_pending.is_set():
                if self._stopped.is_set() and self._pending.empty():
                    break
                try:
                    record = self._pending.get(timeout=.1)
                except Empty:
                    continue
                if self._discard_pending.is_set():
                    break
                with self._drop_lock:
                    dropped, self._dropped = self._dropped, 0
                if dropped:
                    record = {**record, 'dropped_since_write': dropped}
                line = json.dumps(record, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
                handler.handle(logging.makeLogRecord({'msg': line}))
        except Exception:
            self._stopped.set()
            logging.getLogger(__name__).warning('Model safety audit disabled after a log write failure')
        finally:
            if handler:
                handler.close()
