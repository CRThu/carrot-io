"""
Performance benchmarks for FifoBuffer and IoLogger hot paths.
"""
import time
from cio.core.buffer import FifoBuffer
from cio.core.logger import IoLogger


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


def test_benchmark_io_logger_hot_path():
    logger = IoLogger()
    data = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    start = time.perf_counter()

    iterations = 100000
    for _ in range(iterations):
        logger.log_in(data)
        logger.log_out(data)

    elapsed = time.perf_counter() - start
    ops_per_sec = (iterations * 2) / elapsed
    print(f"\nIoLogger Rate: {ops_per_sec:.0f} ops/sec (Elapsed: {elapsed:.4f}s)")
    assert ops_per_sec > 100000
