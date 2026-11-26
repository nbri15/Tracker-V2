"""Small, dependency-free security helpers: password rules and login throttling."""

from __future__ import annotations

import hashlib
import threading
import time

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

# Passwords containing any of these fragments are rejected outright.
_BANNED_FRAGMENTS = (
    'password', 'passw0rd', 'qwerty', 'letmein', 'welcome', 'iloveyou', 'changeme',
    '123456', 'abcdef', 'school', 'teacher', 'classcompass', 'class compass',
)


def password_problem(password: str | None, username: str | None = None) -> str | None:
    """Return a plain-English reason the password is unacceptable, or None if it is fine."""

    value = password or ''
    hint = 'Use at least {n} characters, for example three or four unrelated words.'.format(n=MIN_PASSWORD_LENGTH)
    if len(value) < MIN_PASSWORD_LENGTH:
        return f'Password is too short. {hint}'
    if len(value) > MAX_PASSWORD_LENGTH:
        return f'Password must be no more than {MAX_PASSWORD_LENGTH} characters.'
    lowered = value.lower()
    if len(set(lowered)) < 5:
        return f'Password is too repetitive. {hint}'
    if lowered.isdigit():
        return f'Password cannot be numbers only. {hint}'
    if any(fragment in lowered for fragment in _BANNED_FRAGMENTS):
        return f'Password is too easy to guess. {hint}'
    clean_username = (username or '').strip().lower()
    if len(clean_username) >= 3 and clean_username in lowered:
        return f'Password cannot contain the username. {hint}'
    return None


class LoginThrottle:
    """In-memory limiter for failed sign-ins.

    Two limits apply inside a rolling window: failures for one account from one
    address (``max_attempts``) and failures from one address overall
    (``max_ip_attempts``). State lives in this process only, so it resets on
    restart and is not shared between workers. That is acceptable for one small
    web process, and it still stops simple online guessing.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 900, max_ip_attempts: int = 30, max_entries: int = 5000):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.max_ip_attempts = max_ip_attempts
        self.max_entries = max_entries
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _keys(ip: str, account: str) -> tuple[str, str]:
        return f'acct|{ip}|{account.strip().lower()}', f'ip|{ip}'

    def _recent(self, key: str, now: float) -> list[float]:
        cutoff = now - self.window
        recent = [stamp for stamp in self._failures.get(key, ()) if stamp > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def seconds_until_allowed(self, ip: str, account: str, now: float | None = None) -> int:
        """Return 0 if a sign-in attempt may proceed, else seconds to wait."""

        now = time.time() if now is None else now
        acct_key, ip_key = self._keys(ip, account)
        waits = [0]
        with self._lock:
            for key, limit in ((acct_key, self.max_attempts), (ip_key, self.max_ip_attempts)):
                recent = self._recent(key, now)
                if len(recent) >= limit:
                    waits.append(int(recent[-limit] + self.window - now) + 1)
        return max(waits)

    def record_failure(self, ip: str, account: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            if len(self._failures) >= self.max_entries:
                for key in list(self._failures):
                    self._recent(key, now)
                if len(self._failures) >= self.max_entries:
                    self._failures.clear()
            for key in self._keys(ip, account):
                self._failures.setdefault(key, []).append(now)

    def record_success(self, ip: str, account: str) -> None:
        acct_key, _ = self._keys(ip, account)
        with self._lock:
            self._failures.pop(acct_key, None)


PASSWORD_STAMP_SESSION_KEY = 'pw_stamp'


def password_stamp(password_hash: str | None, user_id: int | None = None) -> str:
    """Short fingerprint of the stored password hash, kept in the session.

    When a password is changed or reset the fingerprint changes, so sessions signed
    in with the old password (on another iPad, say) are signed out. The hash itself
    is never put in the cookie.
    """
    fingerprint = hashlib.sha256((password_hash or '').encode('utf-8')).hexdigest()[:20]
    return f'{user_id}:{fingerprint}'


def stamp_user_id(stamp: str | None) -> str | None:
    return stamp.split(':', 1)[0] if stamp and ':' in stamp else None
