# AGENTS.md - 系统架构与 AI Agent 开发者手册

本文档为 `carrot-io`（包名：`cio`）硬件驱动抽象层项目的**权威架构规范与 AI Agent 开发者手册**。旨在让任何 AI Agent 或工程师**无需逐行阅读源码文件**，即可获得关于本项目的完整、精确心智模型与架构全貌。

---

## 1. 系统五层 Decoupled 架构图

本系统采用 5 层解耦架构：

```text
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                            1. 顶层快捷 API                              │
 │            cio.connect() / cio.scan() / cio.tcp() ...                   │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │
 ┌────────────────────────────────────▼────────────────────────────────────┐
 │                    2. 高层 Composite 协议桥与 Protocol                  │
 │   [AsyncSpiBridge] [AsyncI2cBridge] [RpcRemoteTransport] [ProtocolTrans]│
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ (依赖注入 Dependency Injection / Codec 绑定)
 ┌────────────────────────────────────▼────────────────────────────────────┐
 │                          3. 核心传输抽象层                              │
 │      AsyncStreamTransport (FifoBuffer) / AsyncPacketTransport (Queue)   │
 │         AsyncUartTransport / AsyncI2cTransport / AsyncSpiTransport      │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │
 ┌────────────────────────────────────▼────────────────────────────────────┐
 │                      4. 硬件与网络适配器 Backends                        │
 │  [TcpTransport] [UdpTransport] [SerialTransport] [Ftdi*] [Visa/Usb Stub]│
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ (延迟导入 & 静默探测 Silent Probing)
 ┌────────────────────────────────────▼────────────────────────────────────┐
 │                      5. 系统底层驱动与硬件句柄                           │
 │         Socket OS / PySerial / PyFTDI / C DLLs (visa32, libusb)         │
 └─────────────────────────────────────────────────────────────────────────┘
```

### 层级职责分工

1. **顶层快捷 API (`cio/__init__.py`, `factory.py`)**：统一快捷入口，解析 URL Scheme，处理 Registry 静默探测，实例化传输管道或组合协议桥。
2. **Composite 协议桥层 (`cio/composite/`)**：实现 $O(N+M)$ 依赖注入，将原始传输管道适配为 SPI/I2C/RPC 等高级总线协议，无需重复编写物理后端驱动。
3. **Codec & Protocol 编解码层 (`cio/core/codec.py`, `protocol.py`)**：负责原始 `bytes` 与强类型业务对象之间的双向转换（`LineCodec`, `FixedLengthCodec`, `FramedBinaryCodec`, `StructCodec`）。
4. **核心抽象层 (`cio/core/`)**：定义传输基类 (`AsyncBaseTransport`)、并发保护锁 (`_read_lock`, `_write_lock`)、内存缓冲区 (`FifoBuffer`, `PacketQueue`)、零开销日志 (`RingBufferLogger`) 及分级异常体系。
5. **后端 Backend 层 (`cio/backends/`)**：延迟加载的物理与网络适配器 (`socket.py`, `serial.py`, `ftdi.py`, `visa.py`, `usb.py`)。

---

## 2. 类继承体系与架构派生图

```text
AsyncBaseTransport (抽象基类: open, close, is_open, write, read, query, bind, sync)
 │
 ├── AsyncStreamTransport (无界字节流基类, 关联 FifoBuffer)
 │    ├── AsyncUartTransport (UART 串口参数抽象)
 │    │    ├── SerialTransport (PySerial 硬件串口)
 │    │    └── FtdiUartTransport (PyFTDI 串口驱动)
 │    ├── TcpTransport (TCP Socket asyncio 字节流)
 │    ├── RpcRemoteTransport (远程 RPC 包装管道)
 │    └── MockTransport (内存 Mock 单元测试管道)
 │
 ├── AsyncPacketTransport (有界报文基类, 关联 PacketQueue)
 │    ├── UdpTransport (UDP Datagram 报文 Socket)
 │    └── UsbTransport (PyUSB / libusb 原始 USB 存根)
 │
 ├── AsyncI2cTransport (I2C Master 主机总线)
 │    ├── AsyncI2cBridge (依赖注入 I2C 协议桥)
 │    └── FtdiI2cTransport (PyFTDI I2C 控制器)
 │
 └── AsyncSpiTransport (SPI 全双工总线)
      ├── AsyncSpiBridge (依赖注入 SPI 协议桥)
      └── FtdiSpiTransport (PyFTDI SPI 控制器)

AsyncGpioPin (抽象 GPIO 引脚控制接口)
 ├── FtdiGpioPin (PyFTDI 硬件 GPIO 引脚)
 └── MockGpioPin (内存 Mock GPIO 引脚)
```

---

## 3. 核心数据流与控制时序

### 流程 A：通用 URL 工厂解析 (`cio.connect`)

```text
用户调用 cio.connect("spi+tcp://192.168.1.100:5025?clock=10MHz")
  │
  ├── 1. factory.parse_url() 将 Scheme 拆解为高层 "spi" (Bridge) 与底层 "tcp" (Base Transport)。
  ├── 2. factory.connect("tcp://192.168.1.100:5025") 查询 Registry 中的 "tcp"。
  ├── 3. Registry 执行 probe_fn() -> 返回 True -> 实例化 TcpTransport(host="192.168.1.100", port=5025)。
  └── 4. Factory 将 TcpTransport 注入 AsyncSpiBridge(tcp_transport, clock="10MHz") 中并返回。
```

### 流程 B：流式读取 (`read_until` / `read_exact`)

```text
用户调用 await dev.read_until(b"\n")
  │
  ├── 1. 获取 `_read_lock` (Task 并发安全保护)。
  ├── 2. 检查内部 FifoBuffer 是否已包含 b"\n"。若有，直接切割返回。
  ├── 3. 若无，进入循环拉取：
  │      ├── 调用 `_read_impl()` (从 Socket/串口读取至多 4096 字节)。
  │      ├── 将新字节写入 FifoBuffer (应用 DROP_OLDEST 或 BACKPRESSURE 策略)。
  │      └── 向 RingBufferLogger 追加日志 (仅记录 timestamp, "IN", 原始 bytes)。
  └── 4. 找到 b"\n" 或超时 ( ReadTimeoutError ) 后返回字节。
```

### 流程 C：Protocol Codec 编解码绑定 (`dev.bind(codec)`)

```text
用户绑定 FramedBinaryCodec -> 生成 ProtocolTransport(dev, codec) 实例
  │
  ├── 写入路径: `await proto.write(payload)`
  │     └── `codec.encode(payload)` 构建 [HEADER][LEN][PAYLOAD][CRC] -> 调用 `dev.write(raw_bytes)`
  │
  └── 读取路径: `msg = await proto.read()`
        ├── 从 `dev.read()` 读取原始字节追加至内部 `_recv_buffer`。
        ├── 将 `_recv_buffer` 传入 `codec.decode(buffer)`。
        ├── 若数据不足构成一帧：返回 (None, 0)，继续等待后续字节。
        ├── 若遇到损坏前缀：返回 (None, discard_len)，切割丢弃无用垃圾字节。
        └── 若成功解码帧：返回 (decoded_message, consumed_len) 并切割缓冲区。
```

### 流程 D：静默探测与优雅降级 (`cio.scan()`)

```text
用户调用 cio.scan()
  │
  ├── 遍历已注册 Backend：["tcp", "udp", "serial", "ftdi", "visa", "usb"]
  ├── 对每个 Backend：
  │     ├── 在 try/except 保护下安全执行 `probe_fn()`。
  │     ├── 静默捕获 ImportError, ModuleNotFoundError, OSError, FileNotFoundError, WinError 126。
  │     ├── 若 Probe 失败 (如缺少 PyFTDI 或未安装 visa32.dll)：
  │     │     └── 静默跳过该 Backend，不打日志也不抛出异常。
  │     └── 若 Probe 成功：
  │           └── 调用 `scan_fn()` 收集已发现的物理设备元数据字典。
  └── 返回汇总后的硬件设备列表。
```

---

## 4. 全量模块与符号字典 (File & Symbol Dictionary)

| 文件路径 | 导出符号 | 职责说明与核心逻辑 |
| :--- | :--- | :--- |
| `cio/core/base.py` | `AsyncBaseTransport`, `SyncTransportWrapper` | 传输基类。实现 `_read_lock`, `_write_lock`, `weakref.finalize` 析构、`sync` 属性及 `async with` / `with` 上下文。 |
| `cio/core/stream.py` | `AsyncStreamTransport` | 无界字节流基类。关联 `FifoBuffer`，实现 `read_until(delim)` 与 `read_exact(n)`。 |
| `cio/core/packet.py` | `AsyncPacketTransport` | 有界报文基类。关联 `PacketQueue`，实现 `read_packet()` 与 `write_packet()`。 |
| `cio/core/uart.py` | `AsyncUartTransport` | UART 串口参数控制与抽象 (baudrate, parity, stopbits, bytesize, rtscts)。 |
| `cio/core/i2c.py` | `AsyncI2cTransport` | I2C 主机总线契约 (`read`, `write`, `read_reg`, `write_reg`)。 |
| `cio/core/spi.py` | `AsyncSpiTransport` | SPI 全双工总线契约 (`transfer`)。 |
| `cio/core/gpio.py` | `AsyncGpioPin` | GPIO 引脚契约 (`set_high`, `set_low`, `toggle`, `read_level`, `wait_for_edge`)。 |
| `cio/core/codec.py` | `BaseCodec`, `LineCodec`, `FixedLengthCodec`, `FramedBinaryCodec`, `StructCodec` | 消息编解码器实现。 |
| `cio/core/protocol.py` | `ProtocolTransport` | `bind()` 产生的强类型协议绑定实例。 |
| `cio/core/buffer.py` | `FifoBuffer`, `PacketQueue`, `OverflowPolicy` | 内存缓冲区，支持 `DROP_OLDEST` 与 `BACKPRESSURE` 溢出策略。 |
| `cio/core/logger.py` | `RingBufferLogger`, `LogEntry` | 热路径零开销内存环形日志队列。 |
| `cio/core/exceptions.py` | `TransportError`, `DriverMissingError`, `PythonPackageMissingError`, `CDllMissingError`, `ReadTimeoutError` 等 | 分级自定义异常体系。 |
| `cio/core/registry.py` | `BackendRegistry`, `registry` | 后端注册表，处理静默探测与设备扫描。 |
| `cio/core/factory.py` | `connect()`, `parse_url()` | 通用 URL 解析器与组合工厂。 |
| `cio/backends/socket.py` | `TcpTransport`, `UdpTransport` | Asyncio TCP 字节流与 UDP 报文实现。 |
| `cio/backends/serial.py` | `SerialTransport` | 硬件 UART 串口 PySerial 包装器。 |
| `cio/backends/ftdi.py` | `FtdiUartTransport`, `FtdiI2cTransport`, `FtdiSpiTransport`, `FtdiGpioPin` | PyFTDI 硬件控制器适配器。 |
| `cio/backends/visa.py` | `VisaTransport` | Phase 1 VISA 存根（连接时抛出 `CDllMissingError` 或 `PythonPackageMissingError`）。 |
| `cio/backends/usb.py` | `UsbTransport` | Phase 1 USB 存根。 |
| `cio/composite/gpio.py` | `AsyncGpioBridge` | GPIO 引脚控制协议桥。 |
| `cio/composite/i2c.py` | `AsyncI2cBridge` | I2C 主机总线协议桥。 |
| `cio/composite/spi.py` | `AsyncSpiBridge` | SPI 全双工总线协议桥。 |
| `cio/composite/rpc.py` | `RpcRemoteTransport`, `RpcServer`, `start_rpc_server` | JSON-RPC 2.0 跨机器 PC 硬件代理管道与守护进程网关。 |
| `cio/testing/mock.py` | `MockTransport`, `MockGpioPin` | 内存 Mock 测试双重对象（支持自动应答与发送历史查看）。 |

---

## 5. 核心架构约束与编码准则

1. **核心库零第三方顶层导入**：
   `cio.core.*` 必须仅使用 Python 标准库。第三方扩展包（`pyserial`, `pyftdi`, `pyvisa`, `pyusb`）只能在 `cio.backends.*` 中延迟加载。
2. **热路径零开销日志**：
   `write()` 与 `read()` 内部严禁拼接 Hex 字符串或调用 `print/logger`。仅可调用 `self.logger.log_in(data)` / `log_out(data)` 保存原始 `bytes` 和时间戳。
3. **并发保护锁作用域**：
   所有写入操作必须在 `async with self._write_lock:` 内执行；所有读取操作必须在 `async with self._read_lock:` 内执行。
4. **降级与异常捕获规则**：
   - 在 `probe()` / `scan()` 探测期间：静默捕获 `ImportError`, `ModuleNotFoundError`, `OSError`, `FileNotFoundError`, `WinError 126`。
   - 在 `open()` 显式连接期间：若缺失驱动，必须抛出带有明确安装指引的 `PythonPackageMissingError` 或 `CDllMissingError`。
5. **测试验证**：
   任何代码改动必须通过 `uv run --extra dev pytest -v -m "not hardware"` 验证。
