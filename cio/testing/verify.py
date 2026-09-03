"""
Lightweight Hardware DSL Verification & Assertion Subsystem.
Zero third-party dependencies, single-responsibility data comparison, bitmasking,
aligned colored hex diff rendering, contextvar-isolated sessions, and scoreboard tracking.
"""
from __future__ import annotations

import contextvars
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Strongly-typed assertion result."""
    name: str            # 断言名称
    passed: bool         # 是否通过 (True / False)
    expected_hex: str    # 期望值 Hex 文本
    actual_hex: str      # 实际值 Hex 文本
    diff_line: str       # 格式化好的单行/多行 Hex Diff 文本
    duration_ms: float   # 断言耗时 (毫秒)
    timestamp: float     # 时间戳


def _normalize_data(val: Any) -> tuple[bytes | None, str]:
    """
    Normalize various input formats (bytes, bytearray, int, list[int], hex str)
    to a tuple of (raw_bytes | None, hex_or_repr_string).
    """
    if val is None:
        return None, "None"
    if isinstance(val, bool):
        return (b"\x01" if val else b"\x00"), ("01 (True)" if val else "00 (False)")
    if isinstance(val, (bytes, bytearray, memoryview)):
        b = bytes(val)
        return b, " ".join(f"{x:02X}" for x in b)
    if isinstance(val, int):
        if val < 0:
            return None, str(val)
        if 0 <= val <= 255:
            return bytes([val]), f"{val:02X}"
        bit_len = val.bit_length() or 8
        nbytes = (bit_len + 7) // 8
        b = val.to_bytes(nbytes, byteorder="big")
        return b, " ".join(f"{x:02X}" for x in b)
    if isinstance(val, (list, tuple)) and all(isinstance(x, int) and 0 <= x <= 255 for x in val):
        b = bytes(val)
        return b, " ".join(f"{x:02X}" for x in b)
    if isinstance(val, str):
        clean = val.replace(" ", "").replace("0x", "").replace("0X", "").replace(",", "")
        if clean:
            if len(clean) % 2 != 0:
                clean = "0" + clean
            if all(c in "0123456789abcdefABCDEF" for c in clean):
                try:
                    b = bytes.fromhex(clean)
                    return b, " ".join(f"{x:02X}" for x in b)
                except ValueError:
                    pass
        return None, repr(val)
    return None, repr(val)


def _format_hex_diff(
    name: str,
    passed: bool,
    exp_bytes: bytes | None,
    exp_str: str,
    act_bytes: bytes | None,
    act_str: str,
    mask_str: str | None = None,
    use_color: bool = True,
) -> str:
    """Format aligned hex diff message."""
    tag_pass = "\033[32mPASS\033[0m" if use_color else "PASS"
    tag_fail = "\033[31mFAIL\033[0m" if use_color else "FAIL"
    tag = tag_pass if passed else tag_fail
    mask_suffix = f" (mask=0x{mask_str})" if mask_str else ""
    title = f"{name}{mask_suffix}" if name else mask_suffix.lstrip()

    if passed:
        val_display = f"0x{act_str}" if act_bytes is not None else act_str
        return f"[{tag}] {title}: {val_display}" if title else f"[{tag}] {val_display}"

    # Failure Diff Formatting
    if exp_bytes is not None and act_bytes is not None:
        if len(exp_bytes) != len(act_bytes):
            return (
                f"[{tag}] {title}\n"
                f"  Expected ({len(exp_bytes)}B): 0x{exp_str}\n"
                f"  Actual   ({len(act_bytes)}B): 0x{act_str}"
            )
        # Same length bytes mismatch: build visual pointer
        exp_tokens = exp_str.split(" ")
        act_tokens = act_str.split(" ")
        diff_markers = []
        diff_indices: list[tuple[int, str, str]] = []
        for i, (e, a) in enumerate(zip(exp_tokens, act_tokens)):
            if e != a:
                diff_markers.append("^^")
                diff_indices.append((i, e, a))
            else:
                diff_markers.append("  ")
        marker_line = " ".join(diff_markers)
        if len(exp_tokens) <= 16:
            return (
                f"[{tag}] {title}\n"
                f"  Expected: 0x{exp_str}\n"
                f"  Actual:   0x{act_str}\n"
                f"  Diff:       {marker_line}"
            )
        mismatches_summary = ", ".join(f"@{idx:02X}: exp 0x{e} != act 0x{a}" for idx, e, a in diff_indices[:8])
        if len(diff_indices) > 8:
            mismatches_summary += f", ... ({len(diff_indices)} mismatches total)"
        return (
            f"[{tag}] {title}\n"
            f"  Expected ({len(exp_bytes)}B): 0x{exp_str}\n"
            f"  Actual   ({len(act_bytes)}B): 0x{act_str}\n"
            f"  Mismatches: {mismatches_summary}"
        )

    return f"[{tag}] {title}: Expected {exp_str}, Got {act_str}"


class VerificationSession:
    """
    Assertion and verification session.
    Maintains scoreboard, handles data comparison, mask filtering,
    diff output rendering, event broadcasting, and lifecycle scoping.
    """

    def __init__(
        self,
        continue_on_fail: bool = True,
        auto_dump_on_fail: bool = False,
        print_pass: bool = True,
        print_fail: bool = True,
        dump_hook: Callable[[], str] | None = None,
        print_fn: Callable[[str], None] = print,
    ) -> None:
        self.continue_on_fail = continue_on_fail
        self.auto_dump_on_fail = auto_dump_on_fail
        self.print_pass = print_pass
        self.print_fail = print_fail
        self._dump_hook: Callable[[], str] | None = dump_hook
        self._print_fn: Callable[[str], None] = print_fn
        self._results: list[CheckResult] = []
        self._sinks: list[Callable[[CheckResult], None]] = []
        self._start_time = time.time()
        self._token: contextvars.Token[VerificationSession] | None = None

    def reset(self) -> None:
        """Clear all assertion records and reset timer."""
        self._results.clear()
        self._start_time = time.time()

    @property
    def results(self) -> list[CheckResult]:
        return list(self._results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self._results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self._results if not r.passed)

    @property
    def total_count(self) -> int:
        return len(self._results)

    def add_sink(self, fn: Callable[[CheckResult], None]) -> None:
        """Register a callback listener for check results."""
        if fn not in self._sinks:
            self._sinks.append(fn)

    def remove_sink(self, fn: Callable[[CheckResult], None]) -> None:
        """Unregister a callback listener."""
        if fn in self._sinks:
            self._sinks.remove(fn)

    def set_dump_hook(self, fn: Callable[[], str] | None) -> None:
        """Set a hook to dump communication history on failure."""
        self._dump_hook = fn

    def _record_and_dispatch(self, result: CheckResult, halt: bool = False) -> None:
        self._results.append(result)
        for sink in self._sinks:
            try:
                sink(result)
            except Exception:
                pass

        if result.passed:
            if self.print_pass:
                self._print_fn(result.diff_line)
        else:
            if self.print_fail:
                self._print_fn(result.diff_line)
            if self.auto_dump_on_fail and self._dump_hook is not None:
                try:
                    dump_text = self._dump_hook()
                    if dump_text:
                        self._print_fn("--- Bus Trace on Failure ---")
                        self._print_fn(dump_text)
                        self._print_fn("----------------------------")
                except Exception:
                    pass

            if halt or not self.continue_on_fail:
                raise AssertionError(result.diff_line)

    def compare(
        self,
        actual: Any,
        expected: Any = True,
        name: str = "",
        mask: Any = None,
        halt: bool = False,
    ) -> bool:
        """
        Compare actual against expected value with optional bitmasking.
        """
        t0 = time.perf_counter()
        act_bytes, act_str = _normalize_data(actual)
        exp_bytes, exp_str = _normalize_data(expected)
        use_color = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

        mask_str: str | None = None
        if mask is not None and act_bytes is not None and exp_bytes is not None:
            m_bytes, mask_str = _normalize_data(mask)
            if m_bytes is not None:
                max_len = max(len(act_bytes), len(exp_bytes))
                if len(m_bytes) < max_len:
                    m_bytes = (m_bytes * (max_len // len(m_bytes) + 1))[:max_len]
                else:
                    m_bytes = m_bytes[:max_len]

                pad_act = act_bytes.ljust(max_len, b"\x00")
                pad_exp = exp_bytes.ljust(max_len, b"\x00")
                masked_act = bytes(a & m for a, m in zip(pad_act, m_bytes))
                masked_exp = bytes(e & m for e, m in zip(pad_exp, m_bytes))
                passed = (masked_act == masked_exp) and (
                    len(act_bytes) == len(exp_bytes)
                    or (len(act_bytes) < len(exp_bytes) and all(m == 0 for m in m_bytes[len(act_bytes):]))
                    or (len(exp_bytes) < len(act_bytes) and all(m == 0 for m in m_bytes[len(exp_bytes):]))
                )
            else:
                passed = actual == expected
        elif act_bytes is not None and exp_bytes is not None:
            passed = act_bytes == exp_bytes
        else:
            passed = actual == expected

        t1 = time.perf_counter()
        duration_ms = (t1 - t0) * 1000.0

        diff_line = _format_hex_diff(
            name=name,
            passed=passed,
            exp_bytes=exp_bytes,
            exp_str=exp_str,
            act_bytes=act_bytes,
            act_str=act_str,
            mask_str=mask_str,
            use_color=use_color,
        )

        result = CheckResult(
            name=name,
            passed=passed,
            expected_hex=exp_str,
            actual_hex=act_str,
            diff_line=diff_line,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )

        self._record_and_dispatch(result, halt=halt)
        return passed

    def len(self, data: Any, expected_len: int, name: str = "", halt: bool = False) -> bool:
        """Validate length of collection/bytes."""
        t0 = time.perf_counter()
        actual_len = len(data) if hasattr(data, "__len__") else 0
        passed = actual_len == expected_len
        t1 = time.perf_counter()
        duration_ms = (t1 - t0) * 1000.0
        use_color = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

        chk_name = name or "Length Check"
        tag = ("\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m") if use_color else ("PASS" if passed else "FAIL")
        if passed:
            diff_line = f"[{tag}] {chk_name}: len={actual_len}"
        else:
            diff_line = f"[{tag}] {chk_name}: Expected len={expected_len}, Got len={actual_len}"

        result = CheckResult(
            name=chk_name,
            passed=passed,
            expected_hex=str(expected_len),
            actual_hex=str(actual_len),
            diff_line=diff_line,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )
        self._record_and_dispatch(result, halt=halt)
        return passed

    def mask(self, actual: Any, expected: Any, mask: Any, name: str = "", halt: bool = False) -> bool:
        """Explicit bitmask assertion."""
        return self.compare(actual, expected=expected, name=name, mask=mask, halt=halt)

    def not_none(self, val: Any, name: str = "", halt: bool = False) -> Any:
        """Assert value is not None and return it."""
        t0 = time.perf_counter()
        passed = val is not None
        t1 = time.perf_counter()
        duration_ms = (t1 - t0) * 1000.0
        use_color = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

        chk_name = name or "Not None Check"
        tag = ("\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m") if use_color else ("PASS" if passed else "FAIL")
        diff_line = f"[{tag}] {chk_name}: {repr(val)}" if passed else f"[{tag}] {chk_name}: Expected value not None, Got None"

        result = CheckResult(
            name=chk_name,
            passed=passed,
            expected_hex="not None",
            actual_hex=repr(val),
            diff_line=diff_line,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )
        self._record_and_dispatch(result, halt=halt)
        return val

    def is_none(self, val: Any, name: str = "", halt: bool = False) -> bool:
        """Assert value is None."""
        t0 = time.perf_counter()
        passed = val is None
        t1 = time.perf_counter()
        duration_ms = (t1 - t0) * 1000.0
        use_color = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

        chk_name = name or "Is None Check"
        tag = ("\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m") if use_color else ("PASS" if passed else "FAIL")
        diff_line = f"[{tag}] {chk_name}: None" if passed else f"[{tag}] {chk_name}: Expected None, Got {repr(val)}"

        result = CheckResult(
            name=chk_name,
            passed=passed,
            expected_hex="None",
            actual_hex=repr(val),
            diff_line=diff_line,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )
        self._record_and_dispatch(result, halt=halt)
        return passed

    def raises(
        self,
        exc_type: type[BaseException] | tuple[type[BaseException], ...],
        fn: Callable[..., Any],
        *args: Any,
        name: str = "",
        halt: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Assert callable raises expected exception type."""
        t0 = time.perf_counter()
        chk_name = name or f"Raises {getattr(exc_type, '__name__', str(exc_type))}"
        use_color = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False
        tag_pass = "\033[32mPASS\033[0m" if use_color else "PASS"
        tag_fail = "\033[31mFAIL\033[0m" if use_color else "FAIL"

        try:
            fn(*args, **kwargs)
            t1 = time.perf_counter()
            duration_ms = (t1 - t0) * 1000.0
            diff_line = f"[{tag_fail}] {chk_name}: No exception was raised"
            result = CheckResult(
                name=chk_name,
                passed=False,
                expected_hex=str(exc_type),
                actual_hex="NoException",
                diff_line=diff_line,
                duration_ms=duration_ms,
                timestamp=time.time(),
            )
            self._record_and_dispatch(result, halt=halt)
            return None
        except Exception as e:
            t1 = time.perf_counter()
            duration_ms = (t1 - t0) * 1000.0
            if isinstance(e, exc_type):
                diff_line = f"[{tag_pass}] {chk_name}: Caught {type(e).__name__} ({e})"
                result = CheckResult(
                    name=chk_name,
                    passed=True,
                    expected_hex=str(exc_type),
                    actual_hex=f"{type(e).__name__}: {e}",
                    diff_line=diff_line,
                    duration_ms=duration_ms,
                    timestamp=time.time(),
                )
                self._record_and_dispatch(result, halt=halt)
                return e
            else:
                diff_line = f"[{tag_fail}] {chk_name}: Expected {exc_type}, but got unexpected {type(e).__name__} ({e})"
                result = CheckResult(
                    name=chk_name,
                    passed=False,
                    expected_hex=str(exc_type),
                    actual_hex=f"{type(e).__name__}: {e}",
                    diff_line=diff_line,
                    duration_ms=duration_ms,
                    timestamp=time.time(),
                )
                self._record_and_dispatch(result, halt=halt)
                return None

    def summary(self, print_fn: Callable[[str], None] | None = None) -> bool:
        """
        Print verification summary scoreboard.
        Returns True if failed == 0, False otherwise.
        """
        printer = print_fn or self._print_fn
        total = self.total_count
        passed = self.pass_count
        failed = self.fail_count
        duration = time.time() - self._start_time
        use_color = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

        printer("\n" + "=" * 50)
        printer("           VERIFICATION SUMMARY SCOREBOARD       ")
        printer("=" * 50)
        printer(f"Total Checks  : {total}")
        printer(f"Passed        : {passed}")
        printer(f"Failed        : {failed}")
        printer(f"Duration      : {duration:.3f}s")

        if total == 0:
            status_text = "NO CHECKS"
            status_line = f"\033[33m{status_text}\033[0m" if use_color else status_text
        elif failed == 0:
            status_text = "ALL PASSED"
            status_line = f"\033[32m{status_text}\033[0m" if use_color else status_text
        else:
            status_text = "FAILED"
            status_line = f"\033[31m{status_text}\033[0m" if use_color else status_text

        printer(f"Status        : {status_line}")
        printer("=" * 50 + "\n")

        return failed == 0

    def __enter__(self) -> VerificationSession:
        self._token = _current_session_var.set(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token is not None:
            _current_session_var.reset(self._token)
            self._token = None


_default_session = VerificationSession()
_current_session_var: contextvars.ContextVar[VerificationSession | None] = contextvars.ContextVar(
    "_current_session_var", default=None
)


def get_current_session() -> VerificationSession:
    """Return active VerificationSession in current context, falling back to global default."""
    current = _current_session_var.get()
    return current if current is not None else _default_session


class _AssertionProxy:
    """Proxy forwarding check / require calls to the active VerificationSession."""

    def __init__(self, halt: bool) -> None:
        self._halt = halt

    def __call__(
        self,
        actual: Any,
        expected: Any = True,
        name: str = "",
        mask: Any = None,
    ) -> Any:
        session = get_current_session()
        ok = session.compare(actual, expected=expected, name=name, mask=mask, halt=self._halt)
        return actual if (self._halt and ok) else ok

    def len(self, data: Any, expected_len: int, name: str = "") -> Any:
        session = get_current_session()
        ok = session.len(data, expected_len=expected_len, name=name, halt=self._halt)
        return data if (self._halt and ok) else ok

    def mask(self, actual: Any, expected: Any, mask: Any, name: str = "") -> Any:
        session = get_current_session()
        ok = session.mask(actual, expected=expected, mask=mask, name=name, halt=self._halt)
        return actual if (self._halt and ok) else ok

    def not_none(self, val: Any, name: str = "") -> Any:
        session = get_current_session()
        return session.not_none(val, name=name, halt=self._halt)

    def is_none(self, val: Any, name: str = "") -> bool:
        session = get_current_session()
        return session.is_none(val, name=name, halt=self._halt)

    def raises(
        self,
        exc_type: type[BaseException] | tuple[type[BaseException], ...],
        fn: Callable[..., Any],
        *args: Any,
        name: str = "",
        **kwargs: Any,
    ) -> Any:
        session = get_current_session()
        return session.raises(exc_type, fn, *args, name=name, halt=self._halt, **kwargs)

    def summary(self, print_fn: Callable[[str], None] | None = None) -> bool:
        return get_current_session().summary(print_fn=print_fn)

    def reset(self) -> None:
        get_current_session().reset()

    @property
    def results(self) -> list[CheckResult]:
        return get_current_session().results

    @property
    def pass_count(self) -> int:
        return get_current_session().pass_count

    @property
    def fail_count(self) -> int:
        return get_current_session().fail_count

    @property
    def total_count(self) -> int:
        return get_current_session().total_count


class _VerifyFacade:
    """Unified facade exposing check, require, and session management functions."""

    def __init__(self) -> None:
        self.check = check
        self.require = require

    def __call__(
        self,
        actual: Any,
        expected: Any = True,
        name: str = "",
        mask: Any = None,
    ) -> bool:
        return self.check(actual, expected=expected, name=name, mask=mask)

    def len(self, data: Any, expected_len: int, name: str = "") -> bool:
        return self.check.len(data, expected_len=expected_len, name=name)

    def mask(self, actual: Any, expected: Any, mask: Any, name: str = "") -> bool:
        return self.check.mask(actual, expected=expected, mask=mask, name=name)

    def not_none(self, val: Any, name: str = "") -> Any:
        return self.check.not_none(val, name=name)

    def is_none(self, val: Any, name: str = "") -> bool:
        return self.check.is_none(val, name=name)

    def raises(
        self,
        exc_type: type[BaseException] | tuple[type[BaseException], ...],
        fn: Callable[..., Any],
        *args: Any,
        name: str = "",
        **kwargs: Any,
    ) -> Any:
        return self.check.raises(exc_type, fn, *args, name=name, **kwargs)

    def summary(self, print_fn: Callable[[str], None] | None = None) -> bool:
        return get_current_session().summary(print_fn=print_fn)

    def reset(self) -> None:
        get_current_session().reset()

    def add_sink(self, fn: Callable[[CheckResult], None]) -> None:
        get_current_session().add_sink(fn)

    def remove_sink(self, fn: Callable[[CheckResult], None]) -> None:
        get_current_session().remove_sink(fn)

    def set_dump_hook(self, fn: Callable[[], str] | None) -> None:
        get_current_session().set_dump_hook(fn)


check = _AssertionProxy(halt=False)
require = _AssertionProxy(halt=True)
verify = _VerifyFacade()

__all__ = [
    "CheckResult",
    "VerificationSession",
    "get_current_session",
    "check",
    "require",
    "verify",
]
