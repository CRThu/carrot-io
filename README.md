# carrot-io (cio) - 硬件驱动抽象层

> 极简、零强依赖、优雅静默降级的高性能 Python 3.12+ 硬件驱动抽象层。

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![PyPI Version](https://img.shields.io/pypi/v/carrot-io.svg)](https://pypi.org/project/carrot-io/)
[![Dependencies](https://img.shields.io/badge/dependencies-0%20hard-brightgreen.svg)](#核心特性)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`carrot-io`（包名：`cio`）为工业仪表、串口设备、FTDI 芯片、TCP/UDP 网络管道、总线协议（SPI/I2C/UART）及自定义二进制/文本协议提供了统一的异步 (Asyncio) / 同步 (Sync) 双模抽象接口。

> 📖 **文档导航**：
> - 📘 **[API 参考与开发者速查手册 (API.md)](API.md)**：包含 URL 语法全景表、I2C/SPI/UART/GPIO 总线接口规范、`Verifier` 测试断言框架、RPC 代理及即拷即用模板。
> - 🛠️ **[架构规范与 AI Agent 开发者手册 (AGENTS.md)](AGENTS.md)**：系统 5 层解耦架构、并发锁机制与底层设计约束。
> - 📄 **[CarrotBridge 串口 ASCII 协议规范 (CARROT_PROTOCOL.md)](CARROT_PROTOCOL.md)**：硬件适配层下位机通讯指令集。

---

## 核心架构

`cio` 通过**依赖注入 (Dependency Injection)** 将协议逻辑与物理传输管道解耦，将原本 $N \times M$ 的硬件与总线协议组合复杂度降低至 $O(N+M)$：

```text
                        ┌──────────────────────────────┐
                        │   底层物理传输管道 (M 个)     │
                        │ [TCP] [Serial] [UDP] [FTDI]  │
                        └──────────────┬───────────────┘
                                       │ (依赖注入 Dependency Injection)
                                       ▼
                        ┌──────────────────────────────┐
                        │   高层协议桥与编解码器 (N 个) │
                        │  [SPI]  [I2C]  [RPC] [Codec] │
                        └──────────────┬───────────────┘
                                       ▼
                             统一标准 API 接口
```

---

## 核心特性

- **零强依赖**：核心库仅依赖 Python 3.12+ 标准库，启动时间 < 5ms。
- **双重静默降级**：扫描设备时静默试探驱动；显式连接不可用 Backend 时抛出带明确安装指引的 `DriverMissingError` 异常。
- **流式与块式分叉**：`AsyncStreamTransport`（关联 `FifoBuffer`）用于字节流；`AsyncPacketTransport`（关联 `PacketQueue`）用于报文。
- **零开销热路径日志**：`IoLogger` 线性保存原始 bytes 与时间戳，按需调用 `.history()` 或 `.dump()` 渲染 Hexdump。
- **异步/同步双模**：原生 `asyncio` 支持，并通过 `.sync` 属性无缝适配同步代码库。

---

## 安装说明

### 使用 pip

```bash
# 安装核心库 (零第三方依赖)
pip install carrot-io

# 安装可选扩展
pip install "carrot-io[serial]"   # PySerial 串口支持
pip install "carrot-io[ftdi]"     # PyFTDI 芯片支持
pip install "carrot-io[all]"      # 全量依赖安装
```

### 使用 uv

```bash
# 安装核心库
uv add carrot-io

# 安装可选扩展
uv add "carrot-io[serial]"
uv add "carrot-io[ftdi]"
uv add "carrot-io[all]"
```

---

## 快速上手与使用示例

### 1. TCP SCPI 仪表控制 (以太网)

```python
import asyncio
import cio

async def main():
    async with cio.tcp("192.168.1.100", 5025, timeout=5.0) as dev:
        idn = await dev.query(b"*IDN?\n")
        print("设备标识号:", idn.decode().strip())
        
        await dev.write(b"MEASure:VOLTage:DC?\n")
        val = await dev.read_until(b"\n")
        print("电压测量值:", float(val))

asyncio.run(main())
```

### 2. URL 通用工厂与 SPI+TCP 组合协议桥

```python
import asyncio
import cio

async def main():
    # 通过组合 URL 建立 SPI Over TCP 桥
    async with cio.connect("spi+tcp://192.168.1.100:5025?clock=10MHz") as spi:
        rx = await spi.transfer(b"\x9F\x00\x00\x00")
        print("Flash JEDEC ID:", rx.hex())

asyncio.run(main())
```

### 3. 串口数据帧与 Codec 编解码器绑定

```python
import asyncio
import cio
from cio import FramedBinaryCodec

async def main():
    dev = cio.serial("COM3", baud=115200)
    # 绑定标准工业二进制帧 Codec: [HEADER 0xAA55][LEN 2B][PAYLOAD][CRC16]
    proto = dev.bind(FramedBinaryCodec(header=b"\xAA\x55", crc_type="crc16"))
    
    async with proto:
        await proto.write(b"\x01\x03\x00\x00\x00\x02")
        payload = await proto.read()
        print("解码载荷:", payload.hex())

asyncio.run(main())
```

### 4. 同步代码库阻塞调用 (`.sync`)

```python
import cio

# 使用同步上下文管理器
with cio.serial("COM1", baud=9600).sync as dev:
    dev.write(b"PING\n")
    response = dev.read_until(b"\n")
    print("同步响应:", response)
```

### 5. 无硬件 Mock 单元测试

```python
import asyncio
from cio import MockTransport, LineCodec

async def test_instrument():
    mock_dev = MockTransport()
    mock_dev.add_auto_reply(b"*IDN?", b"MOCK_MULTIMETER_V1\n")
    
    async with mock_dev.bind(LineCodec()) as proto:
        res = await proto.query("*IDN?")
        assert res == "MOCK_MULTIMETER_V1"
```

### 6. 跨网络 RPC 硬件透传代理 (`rpc+serial://`)

```python
import asyncio
import cio

# 1. 远程电脑 B 启动网关守护进程 (暴露本地串口 COM1)
# asyncio.run(cio.start_rpc_server("0.0.0.0", 8000))

# 2. 本地电脑 A 直接通过 URL 代理控制远程串口
async def main():
    url = "rpc+serial://192.168.1.200:8000/COM1?baud=115200"
    async with cio.connect(url) as dev:
        await dev.write(b"HELLO REMOTE COM1\n")
        resp = await dev.read_until(b"\n")
        print("远程串口响应:", resp)

asyncio.run(main())
```

### 7. 硬件控制包协议桥 (`gpio+`, `i2c+`, `spi+`, `frame+`)

```python
import asyncio
import cio

async def main():
    # 通过标准硬件帧协议桥控制 GPIO 引脚与 I2C / SPI 外设 (带 CRC16 校验)
    async with cio.connect("gpio+serial://COM6?baud=115200") as gpio:
        await gpio.set_high()
        level = await gpio.read_level()
        print("GPIO Level:", level)

    async with cio.connect("i2c+serial://COM6?baud=115200") as i2c:
        chip_id = await i2c.read_reg(addr=0x68, reg=0x75, nbytes=1)
        print("I2C Chip ID:", chip_id.hex())

asyncio.run(main())
```


---

## 下位机硬件控制协议规范 (CarrotProtocol V1.0)

`cio` 组合协议桥（`gpio+`, `i2c+`, `spi+`）底层统一采用 **CarrotBridge ASCII 硬件控制协议** 与 MCU / 单片机下位机通信。

包含引脚控制（`IO.W`, `IO.R`, `IO.MODE`, `IO.PULL`）、I2C 物理收发与波特率设置（`IIC.W`, `IIC.R`, `IIC.SPEED`）、SPI 全双工收发与模式设置（`SPI.W`, `SPI.R`, `SPI.T`, `SPI.MODE`, `SPI.SPEED`）及响应规范。

- **完整指令与下行 Payload 解析规范**：请参阅权威文档 [CARROT_PROTOCOL.md](file:///d:/Projects/carrot-io/CARROT_PROTOCOL.md)。


---



### 1. 顶层快捷 API (Top-Level Functions)

#### `cio.connect(url: str, **kwargs) -> AsyncBaseTransport`
通用 URL 工厂入口。解析 Scheme 并实例化对应的 Backend 或组合协议桥。
- **示例**：`cio.connect("serial://COM3?baud=115200")`
- **组合 URL**：`cio.connect("spi+tcp://192.168.1.100:5025")`（自动用 `AsyncSpiBridge` 包装 `TcpTransport`）
- **I2C 组合 URL**：`cio.connect("i2c+serial://COM3?baud=2000000&reg_len=2")`（自动用 `AsyncI2cBridge` 包装 `SerialTransport`，并配置全局默认 16 位寄存器地址长度）

#### `cio.scan(kind: str | None = None) -> list[dict]`
扫描全盘可用硬件设备。内部自动进行静默 Probe 试探，自动跳过未安装依赖的 Backend。
- **参数**：`kind` - 筛选后端类型（如 `"serial"`, `"ftdi"`），为 `None` 时扫描全部。
- **返回**：包含设备元数据的字典列表，例如 `[{"scheme": "serial", "port": "COM3", "description": "USB Serial"}]`。

#### `cio.tcp(host: str = "127.0.0.1", port: int = 5025, timeout: float | None = None, buffer_size: int = 1024*1024) -> TcpTransport`
快捷创建 TCP 字节流传输对象。

#### `cio.udp(host: str = "127.0.0.1", port: int = 5025, timeout: float | None = None, buffer_size: int = 1000) -> UdpTransport`
快捷创建 UDP 报文传输对象。

#### `cio.serial(port: str = "COM1", baud: int = 115200, timeout: float | None = None) -> SerialTransport`
快捷创建串口 UART 传输对象（需安装 `pyserial`）。

#### `cio.ftdi(url: str = "ftdi://ftdi:232h/1", baud: int = 115200, timeout: float | None = None) -> FtdiUartTransport`
快捷创建 FTDI 芯片串口传输对象（需安装 `pyftdi`）。

---

### 2. 基础传输契约分层

#### ① 根基类公共契约 (`AsyncBaseTransport`)
- **`async open() -> None`**：建立物理或网络连接。
- **`async close() -> None`**：关闭连接并释放操作系统/硬件资源。
- **`is_open: bool`**（属性）：获取当前连接状态。
- **`trace: bool`**（属性）：动态开关终端彩色 Hexdump 跟踪。
- **`history(limit: int = 100) -> list[LogEntry]`**：获取最近 `limit` 条 TX/RX/EVT 结构化内存日志。
- **`dump_history(...) -> str`**：按需渲染最近的 Hex/ASCII 交互记录。
- **`bind(codec: BaseCodec) -> ProtocolTransport`**：绑定 Codec 编解码器，返回全新的强类型 Protocol 实例。
- **`sync: SyncTransportWrapper`**（属性）：获取通用同步适配器（如 `dev.sync.write(...)`）。

#### ② 连续流式传输 (`AsyncStreamTransport`)
- **`async write(data: BytesLike, timeout: float | None = None) -> int`**：并发安全地写入原始字节序列。
- **`async read(nbytes: int = -1, timeout: float | None = None) -> bytes`**：从 FIFO 缓冲区或底层流中读取字节（`nbytes=-1` 读取当前可用所有字节）。
- **`async query(cmd: BytesLike, delay: float = 0.0, timeout: float | None = None) -> bytes`**：发送指令并在延时后读取响应。
- **`async read_exact(nbytes: int, timeout: float | None = None) -> bytes`**：精确读取指定字节数。
- **`async read_until(delimiter: bytes = b"\n", timeout: float | None = None) -> bytes`**：流式读取直到遇到定界符。
- **`async flush() -> None`**：清空内部 FIFO 缓冲区。

#### ③ 有界报文传输 (`AsyncPacketTransport`)
- **`async write(data: BytesLike, timeout: float | None = None) -> int`**：发送单条完整报文。
- **`async read(nbytes: int = -1, timeout: float | None = None) -> bytes`**：接收单条完整报文（保持报文边界）。
- **`async query(cmd: BytesLike, delay: float = 0.0, timeout: float | None = None) -> bytes`**：发送报文并等待响应报文。
- **`async flush() -> None`**：清空内部待接收报文队列。

---

### 3. 字节流专属扩展能力 (`AsyncStreamTransport`)

- **`async read_until(delimiter: bytes = b'\n', timeout: float | None = None) -> bytes`**：持续读取字节流直到遇到定界符 `delimiter` 并返回（包含定界符）。
- **`async read_exact(nbytes: int, timeout: float | None = None) -> bytes`**：准确读取 `nbytes` 字节，未集齐前阻塞等待或超时抛出 `ReadTimeoutError`。

---


### 4. 总线协议与 GPIO 专属接口 (Bus & GPIO Interfaces)

#### `AsyncI2cTransport` (I2C 主机总线)
- **`reg_len: int`**：支持通过 URL（如 `?reg_len=2`）或构造函数设置默认寄存器地址字节数（如 16 位地址 `reg_len=2`）。
- **`async read(addr: int, nbytes: int, timeout: float | None = None) -> bytes`**：从从机地址 `addr` 读取 `nbytes` 字节。
- **`async write(addr: int, data: bytes, timeout: float | None = None) -> int`**：向从机地址 `addr` 写入数据。
- **`async read_reg(addr: int, reg: int, nbytes: int = 1, reg_len: int | None = None, timeout: float | None = None) -> bytes`**：读取指定寄存器 `reg`（未指定 `reg_len` 时继承全局默认 `default_reg_len`）。
- **`async write_reg(addr: int, reg: int, data: bytes, reg_len: int | None = None, timeout: float | None = None) -> int`**：写入指定寄存器 `reg`（未指定 `reg_len` 时继承全局默认 `default_reg_len`）。

#### `AsyncSpiTransport` (SPI 主机总线)
- **`async transfer(tx_data: bytes, timeout: float | None = None) -> bytes`**：全双工收发传输，发送 `tx_data` 的同时接收相同长度的 `rx_data`。

#### `AsyncGpioPin` (GPIO 引脚控制)
- **`async set_high() -> None`**：拉高引脚（输出 HIGH/3.3V）。
- **`async set_low() -> None`**：拉低引脚（输出 LOW/0V）。
- **`async toggle() -> None`**：翻转引脚电平。
- **`async read_level() -> bool`**：读取引脚输入电平（`True` 表示 HIGH，`False` 表示 LOW）。
- **`async wait_for_edge(edge: "rising" | "falling" | "both" = "rising", timeout: float | None = None) -> bool`**：等待电平边沿跳变。

---

### 5. 协议编解码器与高层绑定 (`Codecs` & `dev.bind()`)

继承自 `BaseCodec`，包含双向契约：`encode(message) -> bytes` 与 `decode(buffer: bytearray) -> (decoded_msg, consumed_len)`。通过 `dev.bind(codec)` 可直接升级为包含 `write()`、`read()`、`query()`、`flush()` 的强类型 `ProtocolTransport`。

- **`LineCodec(delimiter: bytes = b'\n', encoding: str = 'utf-8')`**：基于文本定界符（如 SCPI / NMEA）的编解码器。
- **`FixedLengthCodec(length: int)`**：定长 N 字节二进制帧编解码器。
- **`FramedBinaryCodec(header=b'\xAA\x55', length_offset=2, length_size=2, length_includes_header=False, crc_type=None, crc_size=None)`**：标准工业二进制帧 `[HEADER][LEN][PAYLOAD][CRC]` 编解码器，支持自动寻头与 `sum8` / `xor8` / `crc16` 或自定义 `Callable[[bytes], bytes | int]` 校验函数。
- **`StructCodec(fmt: str)`**：基于 Python `struct` 格式串（如 `">IH"`）的元组打包/解包解码器。

---


### 6. 远程硬件 RPC 代理网关 (RPC Remote Hardware Proxy & Gateway)

- **`cio.connect("rpc+serial://192.168.1.200:8000/COM1?baud=115200")`**：跨网络透明代理操控远端电脑上的物理串口/硬件。
- **`RpcRemoteTransport(target_url, host, port)`**：客户端 RPC 代理传输管道（基于 JSON-RPC 2.0 异步网关，零第三方依赖）。
- **`start_rpc_server(host="0.0.0.0", port=8000) -> RpcServer`**：在远端电脑上一行代码启动硬件代理网关守护进程，自动将本地所有硬件/串口暴露至网络。

---

### 7. 硬件验证与断言框架 (`check` / `require` / `verify`)

专为芯片验证、自动化冒烟测试和产测脚本设计，提供轻量级扁平断言、位掩码过滤、Hex Diff 现场对比与记分板看板：

```python
from cio import dev, check, require, verify

def run_chip_verify():
    with dev:
        verify.reset()

        # 1. 显式读寄存器 + 预期值比对 (支持 int, hex list, bytes, mask)
        check(dev.read_reg(0x57, 0xFFB1, 1), 0x07, mask=0x07, name="STATUS_REG")
        check(dev.read_reg(0x57, 0xFFB0, 1), 0x10, name="STATUS")

        # 2. 显式写寄存器与回读比对
        dev.write_reg(0x57, 0xFFB4, 0x03)
        check(dev.read_reg(0x57, 0xFFB4, 1), 0x03, name="REG_FFB4")

        # 3. 数组写入与多字节比对
        dev.write_reg(0x57, 0x0020, [0x55] * 16)
        check(dev.read_reg(0x57, 0x0020, 16), [0x55] * 16, name="EEPROM 0x0020")

        # 4. 打印统计看板并返回布尔状态 (True 表示全部通过)
        return verify.summary()

if __name__ == "__main__":
    run_chip_verify()
```

---

### 8. 实时 Trace 追踪与零开销日志

- **URL 一键开启 Trace**：在任意 URL 中添加 `?trace=on` / `?trace=true` 即可实时以微秒级彩色高亮输出底层通信报文。
- **故障现场 Dump**：调用 `dev.dump_history(limit=20)` 导出最近 N 条收发报文。
- **多类型入参支持**：`write()`、`write_reg()`、`transfer()` 等接口均已支持原生传入单个 `int`（如 `0x03`）、整数列表（如 `[0x55] * 16`）及 `bytes`。

---

### 9. 单元测试 Mock 工具 (Testing Utilities)

- **`MockTransport`**：内存模拟传输管道。
  - `push_rx(data: bytes)`：向接收缓冲区注入假数据。
  - `add_auto_reply(pattern: bytes, reply: bytes)`：添加规则匹配自动应答。
  - `tx_history: list[bytes]`：查看发送历史记录。
- **`MockGpioPin(initial_state: bool = False)`**：内存模拟 GPIO 引脚。
  - `state: bool`：当前电平状态。
  - `state_history: list[bool]`：电平变化历史记录。
- **`check` / `require` / `verify`**：硬件 DSL 断言与记分板子系统。

---

## 运行自动化测试与覆盖率

```bash
# 运行单元测试与边界测试
uv run --extra dev pytest -v -m "not hardware"

# 运行测试并生成代码覆盖率报告
uv run --extra dev pytest --cov=cio --cov-report=term-missing -m "not hardware"
```

---

## 开源协议

[MIT License](LICENSE)
