"""
Performance benchmarks for FifoBuffer, TraceController, and SerialTransport hot paths.
"""
import time
from unittest.mock import MagicMock, patch
import pytest

from cio.backends.serial import SerialTransport
from cio.transports.buffer import FifoBuffer
from cio.trace.trace import TraceController


def test_benchmark_fifobuffer_throughput():
    buf = FifoBuffer(max_size=10 * 1024 * 1024)
    chunk = b"X" * 4096
    start = time.perf_counter()

    iterations = 10000
    for _ in range(iterations):
        buf.write(chunk)
        buf.read(4096)

    elapsed = time.perf_counter() - start
    mb_processed = (iterations * 4096) / (1024 * 1024)
    throughput = mb_processed / elapsed
    print(f"\nFifoBuffer Throughput: {throughput:.2f} MB/s (Elapsed: {elapsed:.4f}s)")
    assert throughput > 10.0


def test_benchmark_trace_controller_hot_path():
    trace = TraceController()
    data = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    start = time.perf_counter()

    iterations = 100000
    for _ in range(iterations):
        trace.trace_in(data)
        trace.trace_out(data)

    elapsed = time.perf_counter() - start
    ops_per_sec = (iterations * 2) / elapsed
    print(f"\nTraceController Rate: {ops_per_sec:.0f} ops/sec (Elapsed: {elapsed:.4f}s)")
    assert ops_per_sec > 100000


@pytest.mark.asyncio
async def test_benchmark_serial_latency_anti_regression():
    """
    基准测试：串口交互时延 (RTT) 纯软件仿真基准与防 50ms 假超时退化红线。

    模拟 Windows 真实串口驱动物理行为：
    若请求读取的字节数大于当前实际缓冲区大小 (例如直接索取 4096)，
    Windows 驱动会启动 COMMTIMEOUTS 强制等待 50ms 超时惩罚。

    验证当前“首字节唤醒 (count=1) + 剩余批量拉取”机制在此场景下的平均时延 < 1.0ms，
    严密防止未来代码退化回大块索取而导致 50ms 假超时。
    """
    mock_serial = MagicMock()
    mock_serial.in_waiting = 0

    def mock_read_with_driver_penalty(size: int) -> bytes:
        # 模拟 Windows 驱动超时惩罚：若调用者索取的 size 大于当前就绪量且未走哨兵模式 (size > 1)，
        # 驱动必须等满 timeout (50ms) 才会放行
        if size > 1 and mock_serial.in_waiting < size:
            time.sleep(0.05)
            mock_serial.in_waiting = 0
            return b"[RETURN]: 1\r\n"

        # 哨兵模式阶段 1：首字节唤醒 (size == 1)，微秒级瞬间返回，同时后续字节到达驱动缓冲区
        if size == 1:
            mock_serial.in_waiting = 12
            return b"["

        # 阶段 2：批量吃满已就绪字节 (size == 12)
        mock_serial.in_waiting = 0
        return b"RETURN]: 1\r\n"

    mock_serial.read.side_effect = mock_read_with_driver_penalty
    mock_serial.write.return_value = 10

    with patch("serial.Serial", return_value=mock_serial):
        st = SerialTransport(port="COM_MOCK", baud=2000000)
        await st.open()

        iterations = 50
        start = time.perf_counter()

        for _ in range(iterations):
            mock_serial.in_waiting = 0
            # 模拟执行一次完整的读行交互
            line = await st.read_until(b"\n")
            assert line == b"[RETURN]: 1\r\n"

        elapsed = time.perf_counter() - start
        avg_latency_ms = (elapsed / iterations) * 1000.0
        print(f"\nSerial Mock RTT Latency: {avg_latency_ms:.2f} ms/op (Total: {elapsed:.4f}s for {iterations} ops)")

        # 强断言：平均单次交互开销必须严格 < 1.0ms（正常情况下通常 < 0.2ms）
        # 一旦代码退化回请求 4096 字节，avg_latency_ms 将飙升至 50ms+，立刻熔断报错！
        assert avg_latency_ms < 1.0, f"Serial RTT latency {avg_latency_ms:.2f}ms exceeds 1.0ms limit!"

        await st.close()
