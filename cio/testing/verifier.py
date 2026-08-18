"""
Lightweight Hardware Verification & Assertion Helper (Verifier).
Explicit synchronous test wrapper for bus transports with assertion tracking, bitmasking, step headers, and scoreboard.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
import time
from dataclasses import dataclass
from typing import Any

from cio.core.base import AsyncBaseTransport, SyncTransportWrapper
from cio.core.converters import BytesLike, ensure_bytes


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    expected_hex: str
    actual_hex: str
    duration_ms: float = 0.0


def _to_hex_str(val: Any) -> tuple[bytes, str]:
    """Convert any expected/actual value to (raw_bytes, hex_string)."""
    if isinstance(val, bool):
        return (b"\x01" if val else b"\x00"), ("01" if val else "00")
    if isinstance(val, int):
        if 0 <= val <= 255:
            return bytes([val]), f"{val:02X}"
        bit_len = val.bit_length() or 8
        nbytes = (bit_len + 7) // 8
        b = val.to_bytes(nbytes, byteorder="big")
        return b, " ".join(f"{x:02X}" for x in b)
    try:
        b = ensure_bytes(val)
        return b, " ".join(f"{x:02X}" for x in b)
    except Exception:
        s = str(val)
        return s.encode("utf-8"), s


class Verifier:
    """
    Synchronous hardware testing wrapper and assertion verifier.
    Provides explicit wrappers around dev.read_reg, dev.write_reg, dev.read, dev.write, dev.transfer.
    """

    def __init__(
        self,
        dev: AsyncBaseTransport | SyncTransportWrapper | Any = None,
        continue_on_fail: bool = True,
        auto_dump_on_fail: bool = False,
        print_pass: bool = True,
    ) -> None:
        self.dev = dev
        self.continue_on_fail = continue_on_fail
        self.auto_dump_on_fail = auto_dump_on_fail
        self.print_pass = print_pass
        self.results: list[CheckResult] = []
        self._current_step = 0
        self._start_time = time.time()

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total_count(self) -> int:
        return len(self.results)

    def _run(self, coro: Any) -> Any:
        """Run an async coroutine synchronously if needed."""
        if inspect.isawaitable(coro):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, coro).result()
            return asyncio.run(coro)
        return coro

    def _get_target(self, dev_arg: Any = None) -> Any:
        target = dev_arg if dev_arg is not None else self.dev
        if target is None:
            raise RuntimeError("No transport device bound to Verifier. Pass dev to Verifier(dev) or call with dev=...")
        return target

    # ─── Section Divider & Sleep Helpers ─────────────────────────────────────

    def step(self, title: str) -> None:
        """Print a visually clear section header for a test step."""
        self._current_step += 1
        use_color = sys.stdout.isatty()
        header = f"=== Step {self._current_step}: {title} ==="
        if use_color:
            print(f"\n\033[1;36m{header}\033[0m")
        else:
            print(f"\n{header}")

    def sleep(self, seconds: float) -> None:
        """Sleep for specified seconds and log delay event to trace if available."""
        if self.dev is not None:
            target = getattr(self.dev, "_async", self.dev)
            logger = getattr(target, "logger", None)
            if logger and getattr(logger, "trace", False):
                ms = int(seconds * 1000)
                t_str = time.strftime("%H:%M:%S", time.localtime())
                use_color = sys.stdout.isatty()
                if use_color:
                    print(f"\033[90m[{t_str}]\033[0m \033[33m[DELAY]\033[0m {ms}ms ({seconds}s)")
                else:
                    print(f"[{t_str}] [DELAY] {ms}ms ({seconds}s)")
        time.sleep(seconds)

    # ─── Assertion Engine ───────────────────────────────────────────────────

    def check(self, name: str, expected: Any, actual: Any, mask: Any = None) -> bool:
        """Compare expected vs actual (with optional bitmask), record and print result."""
        exp_bytes, exp_hex = _to_hex_str(expected)
        act_bytes, act_hex = _to_hex_str(actual)

        if mask is not None:
            mask_bytes, mask_hex = _to_hex_str(mask)
            if len(mask_bytes) < len(act_bytes):
                mask_bytes = mask_bytes * (len(act_bytes) // len(mask_bytes) + 1)
            mask_bytes = mask_bytes[: len(act_bytes)]

            masked_act = bytes(a & m for a, m in zip(act_bytes, mask_bytes))
            masked_exp = bytes(e & m for e, m in zip(exp_bytes, mask_bytes))
            ok = masked_act == masked_exp
            name = f"{name} (mask=0x{mask_hex})"
        else:
            ok = exp_bytes == act_bytes

        result = CheckResult(
            name=name,
            passed=ok,
            expected_hex=exp_hex,
            actual_hex=act_hex,
        )
        self.results.append(result)

        use_color = sys.stdout.isatty()
        if ok:
            tag = "\033[32mPASS\033[0m" if use_color else "PASS"
        else:
            tag = "\033[31mFAIL\033[0m" if use_color else "FAIL"

        if ok:
            if self.print_pass:
                print(f"[{tag}] {name}: 0x{act_hex}")
        else:
            print(f"[{tag}] {name}: Expected 0x{exp_hex}, Got 0x{act_hex}")
            if self.auto_dump_on_fail and self.dev is not None:
                print("--- Communication Trace on Failure ---")
                print(self.dev.dump_history(limit=10, color=use_color))
                print("---------------------------------------")

            if not self.continue_on_fail:
                raise AssertionError(f"Verification failed for '{name}': Expected 0x{exp_hex}, Got 0x{act_hex}")

        return ok

    def _handle_error(self, name: str, err: Exception, expected: Any = None) -> None:
        """Helper to record failed exception check."""
        exp_hex = _to_hex_str(expected)[1] if expected is not None else ""
        self.results.append(
            CheckResult(
                name=name,
                passed=False,
                expected_hex=exp_hex,
                actual_hex=f"<ERROR: {type(err).__name__}: {err}>",
            )
        )
        use_color = sys.stdout.isatty()
        tag = "\033[31mFAIL\033[0m" if use_color else "FAIL"
        print(f"[{tag}] {name}: <ERROR: {type(err).__name__}: {err}>")

    # ─── Explicit Bus / Register Wrappers ───────────────────────────────────

    def read_reg(
        self,
        addr: int,
        reg: int,
        nbytes: int = 1,
        *,
        expected: Any = None,
        mask: Any = None,
        name: str | None = None,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
        dev: Any = None,
    ) -> bytes:
        """
        Synchronously read register from I2C device and optionally verify against expected.
        """
        target = self._get_target(dev)
        chk_name = name or f"Read [Addr 0x{addr:02X}, Reg 0x{reg:02X}]"

        try:
            data = self._run(
                target.read_reg(
                    addr=addr,
                    reg=reg,
                    nbytes=nbytes,
                    regfile=regfile,
                    reg_len=reg_len,
                    timeout=timeout,
                )
            )
        except Exception as err:
            if self.continue_on_fail:
                self._handle_error(chk_name, err, expected=expected)
                return b""
            raise

        if expected is not None:
            self.check(chk_name, expected=expected, actual=data, mask=mask)

        return data

    def write_reg(
        self,
        addr: int,
        reg: int,
        data: BytesLike,
        *,
        check: bool = False,
        expected: Any = None,
        mask: Any = None,
        name: str | None = None,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
        dev: Any = None,
    ) -> int:
        """
        Synchronously write register to I2C device with optional check=True automatic readback.
        """
        target = self._get_target(dev)
        chk_name = name or f"Write [Addr 0x{addr:02X}, Reg 0x{reg:02X}]"
        raw_data = ensure_bytes(data)

        try:
            written = self._run(
                target.write_reg(
                    addr=addr,
                    reg=reg,
                    data=raw_data,
                    regfile=regfile,
                    reg_len=reg_len,
                    timeout=timeout,
                )
            )
            if check:
                read_expected = expected if expected is not None else raw_data
                read_name = f"{chk_name} -> Verify"
                read_back = self._run(
                    target.read_reg(
                        addr=addr,
                        reg=reg,
                        nbytes=len(raw_data),
                        regfile=regfile,
                        reg_len=reg_len,
                        timeout=timeout,
                    )
                )
                self.check(read_name, expected=read_expected, actual=read_back, mask=mask)
            return written
        except Exception as err:
            if self.continue_on_fail:
                self._handle_error(chk_name, err)
                return 0
            raise

    def read(
        self,
        nbytes: int = -1,
        *,
        expected: Any = None,
        mask: Any = None,
        name: str | None = None,
        timeout: float | None = None,
        dev: Any = None,
    ) -> bytes:
        """
        Synchronously read raw bytes from Stream/UART device.
        """
        target = self._get_target(dev)
        chk_name = name or f"Stream Read ({nbytes}B)"

        try:
            data = self._run(target.read(nbytes=nbytes, timeout=timeout))
        except Exception as err:
            if self.continue_on_fail:
                self._handle_error(chk_name, err, expected=expected)
                return b""
            raise

        if expected is not None:
            self.check(chk_name, expected=expected, actual=data, mask=mask)

        return data

    def write(
        self,
        data: BytesLike,
        *,
        name: str | None = None,
        timeout: float | None = None,
        dev: Any = None,
    ) -> int:
        """
        Synchronously write raw bytes to Stream/UART device.
        """
        target = self._get_target(dev)
        chk_name = name or "Stream Write"
        raw_data = ensure_bytes(data)

        try:
            return self._run(target.write(data=raw_data, timeout=timeout))
        except Exception as err:
            if self.continue_on_fail:
                self._handle_error(chk_name, err)
                return 0
            raise

    def transfer(
        self,
        tx_data: BytesLike,
        *,
        expected: Any = None,
        mask: Any = None,
        name: str | None = None,
        timeout: float | None = None,
        dev: Any = None,
    ) -> bytes:
        """
        Synchronously transfer data over SPI bus and optionally verify response.
        """
        target = self._get_target(dev)
        chk_name = name or f"SPI Transfer ({len(ensure_bytes(tx_data))}B)"
        raw_tx = ensure_bytes(tx_data)

        try:
            rx_data = self._run(target.transfer(tx_data=raw_tx, timeout=timeout))
        except Exception as err:
            if self.continue_on_fail:
                self._handle_error(chk_name, err, expected=expected)
                return b""
            raise

        if expected is not None:
            self.check(chk_name, expected=expected, actual=rx_data, mask=mask)

        return rx_data

    # ─── Summary Scoreboard ─────────────────────────────────────────────────

    def summary(self) -> bool:
        """Print a summary scoreboard of all verification checks."""
        total = self.total_count
        passed = self.pass_count
        failed = self.fail_count
        duration = time.time() - self._start_time
        use_color = sys.stdout.isatty()

        print("\n" + "=" * 50)
        print("           VERIFICATION SUMMARY SCOREBOARD       ")
        print("=" * 50)
        print(f"Total Checks  : {total}")
        print(f"Passed        : {passed}")
        print(f"Failed        : {failed}")
        print(f"Duration      : {duration:.3f}s")

        if total == 0:
            status_text = "NO CHECKS"
            status_line = f"\033[33m{status_text}\033[0m" if use_color else status_text
        elif failed == 0:
            status_text = "ALL PASSED"
            status_line = f"\033[32m{status_text}\033[0m" if use_color else status_text
        else:
            status_text = "FAILED"
            status_line = f"\033[31m{status_text}\033[0m" if use_color else status_text

        print(f"Status        : {status_line}")
        print("=" * 50 + "\n")

        return total > 0 and failed == 0
