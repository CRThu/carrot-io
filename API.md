# carrot-io (cio) API 参考与开发者速查手册

本文档为 `carrot-io`（Python 导入包名：`cio`）的**权威 API 参考与代码实战速查手册**。为 AI Agent 与自动化测试工程师提供开箱即用的接口契约、参数说明与标准代码模板。

---

## 目录

- [一、顶层入口与连接工厂 (`cio.connect`)](#一顶层入口与连接工厂-cioconnect)
- [二、同步与异步双模调用范式](#二同步与异步双模调用范式)
- [三、总线传输契约与接口方法](#三总线传输契约与接口方法)
  - [1. 基础传输接口 (`AsyncBaseTransport` / `SyncTransportWrapper`)](#1-基础传输接口-asyncbasetransport--synctransportwrapper)
  - [2. 字节流传输 (`AsyncStreamTransport` / `AsyncUartTransport`)](#2-字节流传输-asyncstreamtransport--asyncuarttransport)
  - [3. I2C 主机总线 (`AsyncI2cTransport` / `AsyncI2cBridge`)](#3-i2c-主机总线-asynci2ctransport--asynci2cbridge)
  - [4. SPI 全双工总线 (`AsyncSpiTransport` / `AsyncSpiBridge`)](#4-spi-全双工总线-asyncspitransport--asyncspibridge)
  - [5. GPIO 引脚控制 (`AsyncGpioPin` / `AsyncGpioBridge`)](#5-gpio-引脚控制-asyncgpiopin--asyncgpiobridge)
  - [6. 有界报文传输 (`AsyncPacketTransport`)](#6-有界报文传输-asyncpackettransport)
- [四、硬件测试与断言框架 (`cio.testing.Verifier`)](#四硬件测试与断言框架-ciotestingverifier)
- [五、消息编解码与高层协议 (`cio.core.codec` / `dev.bind`)](#五消息编解码与高层协议-ciocorecodec--devbind)
- [六、远程 RPC 硬件代理网关 (`cio.composite.rpc`)](#六远程-rpc-硬件代理网关-ciocompositerpc)
- [七、数据类型与异常体系](#七数据类型与异常体系)
- [八、即拷即用标准代码模板 (Recipes)](#八即拷即用标准代码模板-recipes)

---

## 一、顶层入口与连接工厂 (`cio.connect`)

### 1. `cio.connect(url: str, **kwargs) -> AsyncBaseTransport`
统一 URL 工厂函数。根据 URL Scheme 自动解析并实例化底层驱动或组合协议桥。

#### URL Scheme 语法全景表

| 类型 | URL 示例 | 说明与常用参数 |
|---|---|---|
| **原生串口** | `serial://COM3?baud=115200` | PySerial 串口，参数：`baud=`, `parity=N/E/O`, `stopbits=1/2`, `bytesize=8`, `timeout=1.0` |
| **原生 TCP** | `tcp://192.168.1.100:5025` | 异步 TCP Socket 流，参数：`timeout=`, `buffer_size=` |
| **原生 UDP** | `udp://192.168.1.100:5025` | 异步 UDP 报文 Socket |
| **FTDI 控制器** | `ftdi://ftdi:232h/1?baud=115200` | PyFTDI 适配器 |
| **I2C 协议桥** | `i2c+serial://COM3?baud=2000000&reg_len=2` | 串口上的 CarrotBridge I2C 主机，参数：`reg_len=1/2/4`, `bus=0` |
| **SPI 协议桥** | `spi+serial://COM3?baud=2000000&cs=0` | 串口上的 CarrotBridge SPI 全双工主机，参数：`cs=0`, `bus=0` |
| **GPIO 协议桥** | `gpio+serial://COM3?pin=1` | 串口上的 CarrotBridge GPIO 引脚控制 |
| **RPC 硬件代理** | `rpc+tcp://192.168.1.50:8000/COM1?baud=115200` | 跨网络机器远程硬件透明代理 |

> **通用参数：**
> - `trace=on` / `trace=true`：自动开启控制台收发通信流实时 Trace。
> - `timeout=2.0`：统一设置默认 I/O 超时（秒）。

### 2. `cio.scan(kind: str | None = None) -> list[dict]`
静默探测系统当前可用的物理硬件与串口设备，无可用设备时静默返回空列表。

### 3. 快捷构造函数
- `cio.serial(port="COM1", baud=115200, **kwargs)`
- `cio.tcp(host="127.0.0.1", port=5025, **kwargs)`
- `cio.udp(host="127.0.0.1", port=5025, **kwargs)`
- `cio.ftdi(url="ftdi://ftdi:232h/1", baud=115200, **kwargs)`
- `cio.start_rpc_server(host="0.0.0.0", port=8000)`

---

## 二、同步与异步双模调用范式

`carrot-io` 核心采用 `asyncio` 原生驱动，并为不同场景提供了清晰的调用范式：

### 1. 自动化硬件测试与断言范式 (使用 `Verifier` 同步包装器，推荐)
在芯片中测、FT 验证及自动化测试脚本中，推荐结合 [cio.testing.Verifier](file:///d:/Projects/carrot-io/API.md#四硬件测试与断言框架-ciotestingverifier) 使用。`with` 同步打开连接后，由 `Verifier` 统一代理执行同步阻塞操作并记录记分板：

```python
import cio
from cio.testing import Verifier

with cio.connect("i2c+serial://COM3?baud=2000000&reg_len=2&trace=on") as dev:
    v = Verifier(dev, continue_on_fail=True)
    v.step("Read Status")
    v.read_reg(0x57, 0xFFB1, expected=0x07, name="STATUS_REG")
    v.write_reg(0x57, 0xFFB4, 0x03, check=True, name="REG_FFB4")
    v.summary()
```

### 2. 原生 Asyncio 异步范式 (全量总线方法与高并发流)
适用于高性能网络转发、异步服务以及对原生 `asyncio` 总线协程的直接调用：

```python
import asyncio
import cio

async def main():
    async with cio.connect("i2c+serial://COM3?baud=2000000&reg_len=2&trace=on") as dev:
        await dev.write_reg(0x57, 0xFFB6, 0xFF)
        val = await dev.read_reg(0x57, 0xFFB6, nbytes=1)
        print("Readback:", val.hex())

asyncio.run(main())
```

### 3. 基础通道同步阻塞范式 (Serial 串口 / TCP SCPI 仪表)
针对纯流式硬件（串口、TCP Socket），`with` 上下文提供原生同步 `write` / `read` / `query` / `read_until` 操作：

```python
import cio

with cio.connect("tcp://192.168.1.100:5025") as dev:
    dev.write(b"*IDN?\n")
    resp = dev.read_until(b"\n")
    print("Instrument:", resp.decode().strip())
```

### 4. 属性转换
- `async_dev.sync`：在异步对象上获取对应的同步包装器 `SyncTransportWrapper`。
- `sync_dev._async`：在同步包装器上获取底层 `AsyncBaseTransport`。

---

## 三、总线传输契约与接口方法

### 1. 基础传输接口 (`AsyncBaseTransport` / `SyncTransportWrapper`)

所有通道与协议桥均具备的基础方法与属性：

| 方法 / 属性 | 签名 (以同步形式展示，异步前加 `await`) | 说明 |
|---|---|---|
| `open()` | `dev.open()` | 打开物理/网络连接（`with`/`async with` 会自动调用） |
| `close()` | `dev.close()` | 关闭连接并释放硬件资源 |
| `is_open` | `bool(dev.is_open)` | 检查连接当前是否开启 |
| `trace` | `dev.trace = True / False` | 动态开启/关闭控制台收发通信 Trace |
| `write()` | `dev.write(data: BytesLike, timeout=None) -> int` | 写入原始数据（线程/协程并发安全保护） |
| `read()` | `dev.read(nbytes: int = -1, timeout=None) -> bytes` | 读取原始字节流数据 |
| `query()` | `dev.query(cmd: BytesLike, delay=0.0, timeout=None) -> bytes` | 发送命令、等待 `delay` 秒后回读响应 |
| `flush()` | `dev.flush()` | 清空内部接收缓冲区 |
| `history()` | `dev.history(limit=100) -> list[LogEntry]` | 获取内存中的历史收发日志条目 |
| `dump_history()` | `dev.dump_history(limit=20, color=False) -> str` | 获取格式化后的 TX/RX 通信 Hex 文本流 |
| `bind()` | `dev.bind(codec: BaseCodec) -> ProtocolTransport` | 绑定编解码器生成强类型协议对象 |

---

### 2. 字节流传输 (`AsyncStreamTransport` / `AsyncUartTransport`)

针对 TCP、Serial 串口、FTDI UART 等流式通道提供高级流操作：

```python
# 同步调用
data = dev.read_exact(16)            # 精确读取 16 字节，不足则等待直到超时
line = dev.read_until(b"\n")         # 读取直到遇到指定分隔符（如换行符）
dev.flush()                          # 清空 FifoBuffer 缓冲数据

# 异步调用 (加 await)
data = await dev.read_exact(16)
line = await dev.read_until(b"\r\n", timeout=1.0)
```

---

### 3. I2C 主机总线 (`AsyncI2cTransport` / `AsyncI2cBridge`)

专为 I2C Master 设计的总线级 API，全面支持单字节/多字节寄存器寻址（异步协程原生调用；同步测试请使用 `Verifier`）：

```python
# 1. 寄存器读写（推荐，自动根据数值或 reg_len 打包寄存器大端地址）
await dev.write_reg(addr=0x57, reg=0xFFB6, data=0xFF)                    # 写单个字节
await dev.write_reg(addr=0x57, reg=0x0020, data=[0x55] * 16)            # 写 16 字节
await dev.write_reg(addr=0x57, reg=0xFFB4, data=0x03, verify=True)       # 写后自动回读并比对，失败抛 IOOperationError

val = await dev.read_reg(addr=0x57, reg=0xFFB1, nbytes=1)                # 读 1 字节 -> bytes
data = await dev.read_reg(addr=0x57, reg=0x0020, nbytes=16)              # 读 16 字节 -> bytes

# 2. 裸 I2C 传输
await dev.write(addr=0x57, data=b"\xFF\xB6\xFF")                         # 向从机直接写原始字节
raw = await dev.read(addr=0x57, nbytes=4)                                # 从从机直接读 4 字节

# 3. 速率配置 (Bridge 专属)
await dev.config_speed(400000)                                           # 设置 I2C 速率 400kHz
```
*(💡 同步测试场景下对应使用 `v.read_reg(...)` 与 `v.write_reg(...)`)*

---

### 4. SPI 全双工总线 (`AsyncSpiTransport` / `AsyncSpiBridge`)

全双工 SPI 传输契约：

```python
# 1. 全双工同步收发 (MOSI 发送的同时 MISO 读取等长数据)
rx_bytes = await dev.transfer([0x9F, 0x00, 0x00, 0x00])                  # 读 SPI Flash JEDEC ID

# 2. 单向写 / 单向读
await dev.write(b"\x06")                                                 # 发送 Write Enable 指令
data = await dev.read(4)                                                 # 读取 4 字节

# 3. SPI 模式与时钟配置 (Bridge 专属)
await dev.config_mode(cpol=0, cpha=0)                                    # 设置 SPI Mode 0
await dev.config_speed(10000000)                                         # 设置 SPI 时钟 10MHz
```
*(💡 同步测试场景下对应使用 `v.transfer(...)`)*

---

### 5. GPIO 引脚控制 (`AsyncGpioPin` / `AsyncGpioBridge`)

引脚级电平与边沿控制契约：

```python
pin = cio.connect("gpio+serial://COM3?pin=1")

await pin.set_high()                                                     # 输出高电平
await pin.set_low()                                                      # 输出低电平
await pin.toggle()                                                       # 翻转电平
level = await pin.read_level()                                           # 读取当前电平 (True/False)
await pin.config_mode("OUT,PP")                                          # 配置模式: "IN", "OUT,PP", "OUT,OD"
await pin.config_pull("UP")                                              # 配置上下拉: "NONE", "UP", "DOWN"
is_triggered = await pin.wait_for_edge(edge="rising", timeout=2.0)       # 等待上升沿 ("rising", "falling", "both")
```

---

### 6. 有界报文传输 (`AsyncPacketTransport`)

针对 UDP Datagram 及 USB Endpoint 等有界消息包传输：

```python
async with cio.connect("udp://192.168.1.100:5025") as dev:
    await dev.write_packet(b"PING")
    packet = await dev.read_packet()
    print("Received Packet:", packet)
```

---

## 四、硬件测试与断言框架 (`cio.testing.Verifier`)

`Verifier` 是专为硬件寄存器与总线测试设计的同步断言验证器，支持执行测试分步、掩码断言、自动重试、通信历史 Trace 现场 Dump 及记分板统计。

### 1. 构造函数
```python
from cio.testing import Verifier

v = Verifier(
    dev=dev,                     # 绑定的硬件设备对象 (同步或异步均可)
    continue_on_fail=True,       # 遇到单项检查失败是否继续向下执行（默认 True）
    auto_dump_on_fail=False,     # 失败时是否自动打印最近 10 条通信原始 Hex Trace
    print_pass=True,             # 是否打印 PASS 行日志
)
```

### 2. 核心测试方法全集

| 方法 | 签名 | 说明 |
|---|---|---|
| `step(title)` | `v.step("Step Name")` | 打印醒目的分步标题分割线（支持终端彩色） |
| `sleep(seconds)` | `v.sleep(0.5)` | 延时等待，若 `trace=on` 会在控制台输出带有精确毫秒数的 `[DELAY]` 记录 |
| `read_reg()` | `v.read_reg(addr, reg, nbytes=1, expected=None, mask=None, name=None)` | 同步读取 I2C 寄存器，若提供 `expected` 则自动断言 |
| `write_reg()` | `v.write_reg(addr, reg, data, check=False, expected=None, mask=None, name=None)` | 同步写 I2C 寄存器；`check=True` 时自动回读校验 |
| `transfer()` | `v.transfer(tx_data, expected=None, mask=None, name=None)` | 同步执行 SPI 全双工传输并校验回显数据 |
| `read()` | `v.read(nbytes=-1, expected=None, mask=None, name=None)` | 读取流式数据并校验 |
| `write()` | `v.write(data, name=None)` | 写入流式数据 |
| `check()` | `v.check(name, expected, actual, mask=None) -> bool` | 通用数据断言（支持 `int`, `bytes`, `list[int]`, 带掩码 `mask`） |
| `summary()` | `v.summary() -> bool` | 打印汇总记分板（Total, Passed, Failed, Duration），全部通过返回 `True` |

---

## 五、消息编解码与高层协议 (`cio.core.codec` / `dev.bind`)

将底层字节流自动封装为强类型消息通道：

```python
from cio.core.codec import LineCodec, FixedLengthCodec, FramedBinaryCodec, StructCodec

# 1. 文本行协议 (SCPI / NMEA)
proto = dev.bind(LineCodec(delimiter=b"\n", encoding="utf-8"))
await proto.write("*IDN?")
resp_str = await proto.read()  # 返回 str，自动剔除 \n

# 2. 定长二进制帧
proto = dev.bind(FixedLengthCodec(length=32))
frame = await proto.read()     # 每次精确返回 32 字节 bytes

# 3. 经典带头带长校验帧: [HEADER 0xAA55][LEN (2B)][PAYLOAD][CRC16]
codec = FramedBinaryCodec(
    header=b"\xAA\x55",
    length_offset=2,
    length_size=2,
    byteorder="big",
    crc_type="crc16",
)
proto = dev.bind(codec)
await proto.write(b"\x01\x02\x03")  # 自动计算长度与 CRC 发送
payload = await proto.read()         # 自动校验 CRC、解包载荷并丢弃前导噪波

# 4. Python Struct 结构体
proto = dev.bind(StructCodec(fmt=">HHLL"))
await proto.write((1, 2, 1000, 2000))
data_tuple = await proto.read()
```

---

## 六、远程 RPC 硬件代理网关 (`cio.composite.rpc`)

跨机器/跨操作系统硬件代理，在目标机启动守护进程，本地透明调用：

### 1. 服务端（连接实际硬件的工控机/树莓派）
```python
import asyncio
import cio

async def main():
    server = await cio.start_rpc_server(host="0.0.0.0", port=8000)
    print("Hardware RPC Gateway running on port 8000...")
    await asyncio.Event().wait()

asyncio.run(main())
```

### 2. 客户端（上位机 / 开发测试机）
```python
import cio

# URL 格式: rpc+<底层类型>://<RPC服务器IP>:<RPC端口>/<远端硬件参数>
url = "rpc+serial://192.168.1.50:8000/COM3?baud=2000000"

with cio.connect(url) as dev:
    dev.write(b"Hello Remote Hardware\n")
```

---

## 七、数据类型与异常体系

### 1. 数据类型归一化 (`BytesLike`)
所有写入入参均声明为 `BytesLike = bytes | bytearray | int | list[int]`，内部通过 `cio.ensure_bytes()` 统一归一化：
- `dev.write(b"\x01\x02")`
- `dev.write([0x01, 0x02, 0x03])`
- `dev.write(0xFF)` （自动识别为 `b"\xFF"`）

### 2. 异常继承树 (`cio.core.exceptions`)
```text
TransportError (基类)
 ├── DriverMissingError (驱动或物理依赖缺失)
 │    ├── PythonPackageMissingError (缺少 pyserial / pyftdi 等 pip 包)
 │    └── CDllMissingError (缺少 visa32.dll / libusb 等 C 动态链接库)
 ├── ConnectionError (连接建立失败)
 │    ├── ConnectTimeoutError (连接超时)
 │    └── ConnectionRefusedError (连接被拒绝)
 ├── IOOperationError (读写 I/O 操作失败)
 │    ├── ReadTimeoutError (读取超时 / read_until 未匹配)
 │    ├── BufferOverflowError (缓冲区溢出)
 │    ├── WriteError (写入失败)
 │    └── FrameChecksumError (帧校验 CRC/CheckSum 错误)
 └── InvalidUrlError (URL Scheme 或参数格式错误)
```

---

## 八、即拷即用标准代码模板 (Recipes)

### 模板 1：I2C 芯片寄存器自动化验证 (同步 Verifier 范式)
```python
from __future__ import annotations
import sys
import cio
from cio.testing import Verifier

PORT = "COM3"
BAUDRATE = 2000000
I2C_ADDR = 0x57

def verify_chip() -> bool:
    with cio.connect(f"i2c+serial://{PORT}?baud={BAUDRATE}&reg_len=2&trace=on") as dev:
        v = Verifier(dev, continue_on_fail=True)

        v.step("Read Status Registers")
        v.read_reg(I2C_ADDR, 0xFFB1, expected=0x07, name="STATUS_REG")
        v.read_reg(I2C_ADDR, 0xFFB0, expected=0x10, name="STATUS")

        v.step("Write & Verify Register")
        v.write_reg(I2C_ADDR, 0xFFB4, 0x03, check=True, name="REG_FFB4")

        v.step("EEPROM Page Write & Readback")
        test_payload = [0x55] * 16
        v.write_reg(I2C_ADDR, 0x0020, test_payload)
        v.sleep(0.5)  # 等待 EEPROM 烧写
        v.read_reg(I2C_ADDR, 0x0020, nbytes=16, expected=test_payload, name="EEPROM 0x0020")

        return v.summary()

if __name__ == "__main__":
    sys.exit(0 if verify_chip() else 1)
```

### 模板 2：SPI Flash ID 读取与全双工通信
```python
import cio

with cio.connect("spi+serial://COM3?baud=2000000&cs=0&trace=on") as dev:
    # 发送 JEDEC ID 读取指令 0x9F，接收 3 字节厂商与设备 ID
    rx = dev.transfer([0x9F, 0x00, 0x00, 0x00])
    print(f"Manufacturer ID: 0x{rx[1]:02X}, Device ID: 0x{rx[2]:02X}{rx[3]:02X}")
```

### 模板 3：SCPI 可编程仪器交互
```python
import cio
from cio.core.codec import LineCodec

with cio.connect("tcp://192.168.1.100:5025?trace=on") as dev:
    proto = dev.bind(LineCodec(delimiter=b"\n"))
    proto.write("*IDN?")
    idn = proto.read(timeout=2.0)
    print("Instrument IDN:", idn)
```
