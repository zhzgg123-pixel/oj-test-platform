"""One execution owner per database, enforced by an operating-system file lock."""
import errno
import os
from pathlib import Path
import threading


class RuntimeBusyError(RuntimeError):
    """Another process already owns execution against this database."""


class ExecutionLease:
    def __init__(self, repository):
        self.repository = repository
        self.path = Path(str(repository.db_path) + '.run.lock')
        self._file = None
        self._guard = threading.Lock()

    def start(self):
        with self._guard:
            if self._file is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Never unlink the lock file: doing so can create two different locked inodes.
            lock_file = open(self.path, 'a+b', buffering=0)
            try:
                lock_file.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        # Locking beyond EOF is supported; do not write into another owner's byte.
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise RuntimeBusyError('database already has an execution owner; choose a different --db') from None
                    raise
                # Only the lock holder may migrate or recover old active tasks.
                self.repository.initialize()
                self.repository.recover_interrupted()
            except BaseException:
                lock_file.close()
                raise
            self._file = lock_file

    def close(self):
        with self._guard:
            if self._file is not None:
                # Closing releases the OS lock, including on process death.
                self._file.close()
                self._file = None
