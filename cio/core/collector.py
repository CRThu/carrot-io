"""
DataCollector - Lightweight multi-channel measurement collector and pipeline.
Each tag is naturally an independent 1D time-series vector (no matrix assumptions).
"""
from __future__ import annotations

import csv
import io
import math
import os
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True, frozen=True)
class DataPoint:
    """Immutable single measurement data point."""

    timestamp: float
    tag: str
    value: Any
    unit: str = ""
    raw: Any = None

    @property
    def time_str(self) -> str:
        """Formatted timestamp HH:MM:SS.mmm."""
        t = time.localtime(self.timestamp)
        ms = int((self.timestamp % 1) * 1000)
        return f"{time.strftime('%H:%M:%S', t)}.{ms:03d}"


class DataCollector:
    """
    Lightweight, multi-channel measurement collector and persistence pipeline.
    Each tag is an independent 1D vector of measurements over time.
    Zero third-party dependencies, thread-safe, crash-safe streaming to disk.
    """

    def __init__(
        self,
        filepath: str | None = None,
        transform: Callable[[Any], Any] | dict[str, Callable[[Any], Any]] | None = None,
        auto_flush: bool = True,
    ) -> None:
        self.filepath = filepath
        self.transform = transform
        self.auto_flush = auto_flush

        # Tag-indexed 1D time-series vectors
        self._values: dict[str, list[Any]] = {}
        self._timestamps: dict[str, list[float]] = {}
        self._units: dict[str, str] = {}
        self._points: list[DataPoint] = []  # Chronological order of all events
        self._lock = threading.Lock()

        self._file: Any = None
        self._csv_writer: Any = None

        if self.filepath:
            self._init_file(self.filepath)

    def _init_file(self, path: str) -> None:
        is_new = not os.path.exists(path) or os.path.getsize(path) == 0
        self._file = open(path, "a", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._file)
        if is_new:
            self._csv_writer.writerow(["timestamp", "time_str", "tag", "value", "unit"])
            if self.auto_flush:
                self._file.flush()

    def _apply_transform(self, raw_val: Any, tag: str) -> Any:
        if self.transform is None:
            return raw_val
        if isinstance(self.transform, dict):
            fn = self.transform.get(tag)
            return fn(raw_val) if fn else raw_val
        if callable(self.transform):
            return self.transform(raw_val)
        return raw_val

    def _append_single(self, ts: float, tag: str, val: Any, unit: str, raw: Any) -> None:
        """Internal helper to append a single point into tag's 1D vector."""
        calibrated = self._apply_transform(val, tag)
        if tag not in self._values:
            self._values[tag] = []
            self._timestamps[tag] = []
        self._values[tag].append(calibrated)
        self._timestamps[tag].append(ts)
        if unit:
            self._units[tag] = unit

        pt = DataPoint(timestamp=ts, tag=tag, value=calibrated, unit=unit or self._units.get(tag, ""), raw=raw)
        self._points.append(pt)

        if self._csv_writer:
            self._csv_writer.writerow([f"{pt.timestamp:.6f}", pt.time_str, pt.tag, pt.value, pt.unit])
            if self.auto_flush and self._file:
                self._file.flush()

    def _is_sequence(self, val: Any) -> bool:
        """Check if value is a sequence of numbers (vector)."""
        return hasattr(val, "__iter__") and not isinstance(val, (str, bytes, bytearray, dict))

    def collect(
        self,
        data: Any = None,
        *,
        tag: str = "default",
        unit: str = "",
        **kwargs: Any,
    ) -> None:
        """
        Unified single ingestion method.
        Every tag represents an independent 1D vector:
        - col.collect(5.01, tag="CH1")          -> appends 1 element to CH1 vector
        - col.collect([1.1, 1.2], tag="CH1")     -> appends 2 elements to CH1 vector
        - col.collect(CH1=5.01, CH2=[1.1, 1.2])  -> appends to respective tag vectors
        """
        now = time.time()
        with self._lock:
            # 1. Multi-channel keyword ingestion
            if kwargs:
                for k, v in kwargs.items():
                    if self._is_sequence(v):
                        for item in v:
                            self._append_single(now, k, item, unit, item)
                    else:
                        self._append_single(now, k, v, unit, v)

            # 2. Positional data ingestion
            if data is not None:
                if self._is_sequence(data):
                    for item in data:
                        self._append_single(now, tag, item, unit, item)
                else:
                    self._append_single(now, tag, data, unit, data)

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Direct callable alias to collect()."""
        self.collect(*args, **kwargs)

    def __getitem__(self, item: str | tuple[str, Any]) -> Any:
        """
        Direct indexing and slicing support:
        - col["CH1"]       -> returns the full 1D values vector list
        - col["CH1"][0]    -> first point
        - col["CH1"][:100] -> first 100 points
        - col["CH1", 0]    -> direct 2D index shortcut
        - col["CH1", :100] -> direct 2D slice shortcut
        """
        with self._lock:
            if isinstance(item, tuple):
                tag, sub = item
                vec = self._values.get(tag, [])
                return vec[sub]
            return list(self._values.get(item, []))

    def tags(self) -> list[str]:
        """Return list of distinct recorded tags/channels."""
        with self._lock:
            return list(self._values.keys())

    def get(self, tag: str | None = None) -> list[DataPoint]:
        """Get DataPoint objects, optionally filtered by tag."""
        with self._lock:
            if tag is None:
                return list(self._points)
            return [p for p in self._points if p.tag == tag]

    def values(self, tag: str | None = None) -> list[Any]:
        """Get 1D values vector for a tag, or all values."""
        with self._lock:
            if tag is not None:
                return list(self._values.get(tag, []))
            return [p.value for p in self._points]

    def timestamps(self, tag: str) -> list[float]:
        """Get 1D timestamps vector for a specific tag."""
        with self._lock:
            return list(self._timestamps.get(tag, []))

    def last(self, tag: str | None = None) -> Any:
        """Get the most recent value for a given tag, or overall."""
        with self._lock:
            if tag is not None:
                vec = self._values.get(tag)
                return vec[-1] if vec else None
            return self._points[-1].value if self._points else None

    def min(self, tag: str) -> float | int | None:
        """Get minimum value of tag's 1D vector."""
        vals = [v for v in self.values(tag) if isinstance(v, (int, float)) and not math.isnan(v)]
        return min(vals) if vals else None

    def max(self, tag: str) -> float | int | None:
        """Get maximum value of tag's 1D vector."""
        vals = [v for v in self.values(tag) if isinstance(v, (int, float)) and not math.isnan(v)]
        return max(vals) if vals else None

    def mean(self, tag: str) -> float | None:
        """Get arithmetic average of tag's 1D vector."""
        vals = [v for v in self.values(tag) if isinstance(v, (int, float)) and not math.isnan(v)]
        return sum(vals) / len(vals) if vals else None

    def median(self, tag: str) -> float | int | None:
        """Get median (中位数/中值) of tag's 1D vector, robust against glitches and spikes."""
        vals = [v for v in self.values(tag) if isinstance(v, (int, float)) and not math.isnan(v)]
        return statistics.median(vals) if vals else None

    def summary(self) -> dict[str, dict[str, Any]]:
        """Return structured summary dictionary of all recorded 1D channel vectors."""
        res: dict[str, dict[str, Any]] = {}
        for tag in self.tags():
            vals = self.values(tag)
            num_vals = [v for v in vals if isinstance(v, (int, float)) and not math.isnan(v)]
            unit = self._units.get(tag, "")
            res[tag] = {
                "count": len(vals),
                "min": min(num_vals) if num_vals else None,
                "max": max(num_vals) if num_vals else None,
                "mean": sum(num_vals) / len(num_vals) if num_vals else None,
                "median": statistics.median(num_vals) if num_vals else None,
                "last": vals[-1] if vals else None,
                "unit": unit,
            }
        return res

    def print_summary(self) -> None:
        """Print clean ASCII summary dashboard table to stdout with Median included."""
        info = self.summary()
        if not info:
            print("[Collector] No measurement points recorded.")
            return

        header = f"┌{'─'*14}┬{'─'*8}┬{'─'*10}┬{'─'*10}┬{'─'*10}┬{'─'*10}┬{'─'*10}┬{'─'*8}┐"
        title = f"│ {'Metric/Tag':<12} │ {'Count':<6} │ {'Min':<8} │ {'Max':<8} │ {'Mean':<8} │ {'Median':<8} │ {'Last':<8} │ {'Unit':<6} │"
        divider = f"├{'─'*14}┼{'─'*8}┼{'─'*10}┼{'─'*10}┼{'─'*10}┼{'─'*10}┼{'─'*10}┼{'─'*8}┤"
        footer = f"└{'─'*14}┴{'─'*8}┴{'─'*10}┴{'─'*10}┴{'─'*10}┴{'─'*10}┴{'─'*10}┴{'─'*8}┘"

        def _fmt(val: Any) -> str:
            if val is None:
                return "-"
            if isinstance(val, float):
                return f"{val:.3f}"
            return str(val)

        print(header)
        print(title)
        print(divider)
        for tag, stat in info.items():
            line = (
                f"│ {tag:<12} │ {stat['count']:<6} │ {_fmt(stat['min']):<8} │ "
                f"{_fmt(stat['max']):<8} │ {_fmt(stat['mean']):<8} │ {_fmt(stat['median']):<8} │ "
                f"{_fmt(stat['last']):<8} │ {stat['unit']:<6} │"
            )
            print(line)
        print(footer)

    def to_csv(
        self,
        filepath: str | None = None,
        *,
        tag: str | None = None,
    ) -> str:
        """
        Export recorded points to CSV file or return CSV string.
        - filepath: output file path (optional, uses self.filepath if omitted)
        - tag: filter by specific channel (e.g. tag="CH1")
        """
        target_path = filepath or self.filepath
        with self._lock:
            pts = self._points if tag is None else [p for p in self._points if p.tag == tag]

            if target_path:
                with open(target_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "time_str", "tag", "value", "unit"])
                    for pt in pts:
                        writer.writerow([f"{pt.timestamp:.6f}", pt.time_str, pt.tag, pt.value, pt.unit])
                return target_path
            else:
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["timestamp", "time_str", "tag", "value", "unit"])
                for pt in pts:
                    writer.writerow([f"{pt.timestamp:.6f}", pt.time_str, pt.tag, pt.value, pt.unit])
                return buf.getvalue()

    def to_dict(self) -> dict[str, list[Any]]:
        """Return dict of 1D vectors: {tag: [values]}."""
        with self._lock:
            return {k: list(v) for k, v in self._values.items()}

    def to_numpy(self, tag: str | None = None) -> Any:
        """
        Convert tag's 1D vector to numpy.ndarray.
        Requires numpy installed; raises ImportError with friendly message otherwise.
        """
        try:
            import numpy as np  # type: ignore
        except (ImportError, ModuleNotFoundError) as err:
            raise ImportError("NumPy is required to use to_numpy(). Please install it via 'pip install numpy'.") from err

        vals = self.values(tag)
        return np.array(vals)

    def flush(self) -> None:
        """Flush file buffer to physical disk."""
        with self._lock:
            if self._file:
                self._file.flush()

    def clear(self) -> None:
        """Clear all in-memory recorded vectors."""
        with self._lock:
            self._values.clear()
            self._timestamps.clear()
            self._units.clear()
            self._points.clear()

    def close(self) -> None:
        """Close opened file handle safely."""
        with self._lock:
            if self._file:
                try:
                    self._file.flush()
                    self._file.close()
                except Exception:
                    pass
                self._file = None
                self._csv_writer = None

    def __enter__(self) -> DataCollector:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __len__(self) -> int:
        with self._lock:
            return len(self._points)


# Convenient alias
Collector = DataCollector
