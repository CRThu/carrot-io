"""
Unit tests for cio.core.collector (DataCollector / Collector).
"""
import os
import tempfile
import threading
import pytest

import cio
from cio import Collector, DataCollector, DataPoint


def test_collector_basic_and_callable():
    col = Collector()
    assert len(col) == 0

    # 1. 关键字参数多通道同时打点
    col.collect(CH1=5.01, CH2=3.32, TEMP=25.4)
    assert len(col) == 3
    assert col.tags() == ["CH1", "CH2", "TEMP"]

    # 2. 单点指定参数
    col.collect(5.05, tag="CH1", unit="V")
    assert len(col) == 4
    assert col.values("CH1") == [5.01, 5.05]
    # 支持直接像字典/向量一样索引
    assert col["CH1"] == [5.01, 5.05]
    assert len(col.timestamps("CH1")) == 2
    assert col.last("CH1") == 5.05

    # 3. 直接调用实例语法糖 (__call__)
    col(CH1=4.98, CH2=3.30)
    assert len(col) == 6
    assert col["CH1"] == [5.01, 5.05, 4.98]
    assert col.last("CH1") == 4.98
    assert col.last("CH2") == 3.30


def test_collector_batch_injection():
    col = Collector()

    # 1. 默认即为向量 (自动展开存入该 tag 对应的一维序列)
    raw_wave = [1.0, 2.0, 3.0, 4.0, 5.0]
    col.collect(raw_wave, tag="WAVE", unit="V")
    assert len(col) == 5
    assert col["WAVE"] == [1.0, 2.0, 3.0, 4.0, 5.0]

    # 2. 关键字参数中传入向量也自动存入各 tag 对应向量
    col(V_MULTI=[10.0, 20.0, 30.0])
    assert len(col) == 8
    assert col["V_MULTI"] == [10.0, 20.0, 30.0]

    # 3. 再次向同一 tag 追加单个点或向量切片
    col.collect([6.0, 7.0], tag="WAVE")
    assert len(col["WAVE"]) == 7
    assert col["WAVE"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]


def test_collector_transform_functions():
    # 1. 全局单个转换函数
    col1 = Collector(transform=lambda raw: float(raw) * 2.0)
    col1.collect(10, tag="CH1")
    col1.collect("20", tag="CH2")
    assert col1.values("CH1") == [20.0]
    assert col1.values("CH2") == [40.0]

    # 2. 针对各 Tag 分别配置转换函数
    col2 = Collector(
        transform={
            "VOLT": lambda x: float(x) * 1.002,
            "ADC": lambda x: int(x, 16) if isinstance(x, str) else int(x),
        }
    )
    col2.collect("10.0", tag="VOLT")
    col2.collect("0x1A", tag="ADC")
    col2.collect("UNTOUCHED", tag="OTHER")

    assert col2.last("VOLT") == pytest.approx(10.02)
    assert col2.last("ADC") == 26
    assert col2.last("OTHER") == "UNTOUCHED"


def test_collector_statistics():
    col = Collector()
    # 注入数据，包括偶数与奇数测试，并故意注入毛刺验证 median 鲁棒性
    # 正常电压 5.0, 5.0, 5.1, 4.9，带一个 100.0 的瞬态干扰毛刺
    col.collect([5.00, 5.00, 5.10, 4.90, 100.0], tag="GLITCH")

    assert col.min("GLITCH") == 4.90
    assert col.max("GLITCH") == 100.0
    # Mean 被毛刺拉高到 24.0
    assert col.mean("GLITCH") == pytest.approx(24.0)
    # Median 完美抵抗毛刺干扰，保持在 5.00！
    assert col.median("GLITCH") == pytest.approx(5.00)

    # 空 tag 统计返回 None
    assert col.min("NON_EXISTENT") is None
    assert col.max("NON_EXISTENT") is None
    assert col.mean("NON_EXISTENT") is None
    assert col.median("NON_EXISTENT") is None

    # 汇总字典
    summary = col.summary()
    assert "GLITCH" in summary
    assert summary["GLITCH"]["count"] == 5
    assert summary["GLITCH"]["min"] == 4.90
    assert summary["GLITCH"]["max"] == 100.0
    assert summary["GLITCH"]["mean"] == pytest.approx(24.0)
    assert summary["GLITCH"]["median"] == pytest.approx(5.00)

    # 测试看板打印包含 Median 列且不崩溃
    col.print_summary()

    # 测试空记录打印
    empty_col = Collector()
    empty_col.print_summary()


def test_collector_streaming_csv_crash_safe():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        csv_path = tmp.name

    try:
        # 1. 实时流式写入
        with Collector(filepath=csv_path, auto_flush=True) as col:
            col.collect(5.01, tag="CH1", unit="V")
            col.collect(3.30, tag="CH2", unit="V")

            # 验证在 with 内部已经实时写入磁盘物理文件 (Crash-Safe)
            with open(csv_path, "r", encoding="utf-8") as f:
                content = f.read()
                assert "CH1" in content
                assert "5.01" in content
                assert "CH2" in content

        # 2. 退出 with 自动关闭，重新以追加模式打开
        with Collector(filepath=csv_path) as col2:
            col2.collect(5.05, tag="CH1", unit="V")

        with open(csv_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            # 1行表头 + 3行数据
            assert len(lines) == 4
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)


def test_collector_export_formats():
    col = Collector()
    col.collect([10, 20, 30, 40, 50], tag="A")
    col.collect(99, tag="B")

    # 1. 索引与切片访问测试
    # A) col[key][0] 与 col[key][:2]
    assert col["A"][0] == 10
    assert col["A"][:3] == [10, 20, 30]
    assert col["A"][-1] == 50

    # B) 2D 快捷切片 col[key, 0] 与 col[key, :3]
    assert col["A", 0] == 10
    assert col["A", :3] == [10, 20, 30]

    # 2. to_dict
    d = col.to_dict()
    assert d["A"] == [10, 20, 30, 40, 50]
    assert d["B"] == [99]

    # 3. to_csv 全量导出
    csv_str = col.to_csv()
    assert "A" in csv_str
    assert "B" in csv_str

    # 4. to_csv 单独导出指定 tag 通道
    csv_a = col.to_csv(tag="A")
    assert "A" in csv_a
    assert "B" not in csv_a
    lines = [l for l in csv_a.strip().split("\n") if l]
    # 1 表头 + 5 个数据点
    assert len(lines) == 6

    # 5. to_numpy
    try:
        import numpy as np

        arr = col.to_numpy("A")
        assert isinstance(arr, np.ndarray)
        assert list(arr) == [10, 20, 30, 40, 50]
    except ImportError:
        pass


def test_collector_thread_safety():
    col = Collector()

    def worker(worker_id: int):
        for i in range(100):
            col.collect(i, tag=f"WORKER_{worker_id}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

def test_collector_edge_cases_and_coverage():
    col = Collector()

    # 1. 空 last
    assert col.last("UNKNOWN") is None

    # 2. clear
    col.collect("TEXT_VAL", tag="STR_TAG")
    assert len(col) == 1
    col.flush()
    col.clear()
    assert len(col) == 0

    # 3. to_csv 传不同文件路径
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        path1 = tmp.name
    try:
        col.collect(100, tag="TEST")
        col.to_csv(path1)
        with open(path1, "r", encoding="utf-8") as f:
            assert "100" in f.read()
    finally:
        if os.path.exists(path1):
            os.remove(path1)

    # 4. to_numpy 模拟未安装异常
    import sys
    from unittest.mock import patch

    with patch.dict(sys.modules, {"numpy": None}):
        with pytest.raises(ImportError) as exc_info:
            col.to_numpy("TEST")
        assert "NumPy is required" in str(exc_info.value)

    # 5. print_summary 中包含字符串和浮点数
    col.collect("NON_NUMERIC", tag="STR_TAG")
    col.print_summary()

