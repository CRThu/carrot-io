# carrot-io (cio) API 参考与开发者速查手册

本文档为 `carrot-io`（Python 导入包名：`cio`）的**权威 API 参考与代码实战速查手册**。为 AI Agent 与自动化测试工程师提供开箱即用的接口契约、参数说明与标准代码模板。

---

## 目录

- [一、顶层入口与连接工厂 (`cio.connect`)](#一顶层入口与连接工厂-cioconnect)
  - [1. URL Scheme 语法全景表](#1-cioconnecturl-str-kwargs---asyncbasetransport)
  - [2. `cio.scan` 设备静默探测](#2-cioscankind-str--none--none---listdict)
  - [3. 极简 DSL 单例与环境变量注入 (`from cio import dev`)](#3-极简-dsl-单例与环境变量注入-from-cio-import-dev)
  - [4. 快捷构造函数](#4-快捷构造函数)
  - [5. 单物理底座多路复用（I2C + SPI + GPIO 共用同一串口）](#5-单物理底座多路复用i2c--spi--gpio-共用同一串口)
  - [6. 沁恒 CH347 高速 USB 多协议硬件底座与双串口并发](#6-沁恒-ch347-高速-usb-多协议硬件底座与双串口并发)
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
| **CH347 底座** | `ch347://0` | 沁恒 CH347 高速多协议底座，参数：`index=0` |
| **CH347 I2C** | `i2c+ch347://0?frequency=400000` | CH347 硬件 I2C 主机，参数：`frequency=`, `reg_len=1/2/4` |
| **CH347 SPI** | `spi+ch347://0?frequency=15000000&mode=0&cs=0` | CH347 硬件 SPI 主机，参数：`frequency=`, `mode=0/1/2/3`, `cs=0/1` |
| **CH347 GPIO** | `gpio+ch347://0?pin=3` | CH347 硬件 GPIO 引脚控制，参数：`pin=0~7` |
| **I2C 协议桥** | `i2c+serial://COM3?baud=2000000&reg_len=2` | 串口上的 CarrotBridge I2C 主机，参数：`reg_len=1/2/4`, `bus=0` |
| **SPI 协议桥** | `spi+serial://COM3?baud=2000000&cs=0` | 串口上的 CarrotBridge SPI 全双工主机，参数：`cs=0`, `bus=0` |
| **GPIO 协议桥** | `gpio+serial://COM3?pin=1` | 串口上的 CarrotBridge GPIO 引脚控制 |
| **RPC 硬件代理** | `rpc+tcp://192.168.1.50:8000/COM1?baud=115200` | 跨网络机器远程硬件透明代理 |

> **通用参数：**
> - `trace=on` / `trace=true`：自动开启控制台收发通信流实时 Trace。
> - `timeout=2.0`：统一设置默认 I/O 超时（秒）。

### 2. `cio.scan(kind: str | None = None) -> list[dict]`
静默探测系统当前可用的物理硬件与串口设备，无可用设备时静默返回空列表。

### 3. 极简 DSL 单例与环境变量注入 (`from cio import dev`)

为支持极简测试脚本与领域特定语言（DSL）调用，`cio` 提供开箱即用的模块级惰性单例 `dev` 与本级目录 `.env` 环境变量注入：

```bash
# 当前工作目录下的 .env
CIO_DEVICE="i2c+serial://COM3?baud=2000000&reg_len=2"
CIO_DEVICE_POWER="serial://COM4?baud=9600"
```

```python
# 01_ee_clear.py —— 无需 with，无需显式 connect，开箱即用
from cio import dev

# 1. 默认设备操作 (读取 CIO_DEVICE)
dev.write_reg(0x57, 0xFFB6, 0xFF)
data = dev.read_reg(0x57, 0xFFB0, 1)

# 2. 具名多设备下标访问 (读取 CIO_DEVICE_POWER)
dev["power"].write("VSET 3.3\n")
```

> **安全与生命周期保障：**
> - **惰性连接**：`from cio import dev` 在导入阶段零副作用，只有首次调用方法时才建立硬件连接。
> - **`atexit` 自动安全回收**：脚本正常结束或异常崩溃退出时，底层自动安全关闭串口与物理连接，彻底杜绝操作系统端口死锁。

### 4. 快捷构造函数
- `cio.serial(port="COM1", baud=115200, **kwargs)`
- `cio.tcp(host="127.0.0.1", port=5025, **kwargs)`
- `cio.udp(host="127.0.0.1", port=5025, **kwargs)`
- `cio.ftdi(url="ftdi://ftdi:232h/1", baud=115200, **kwargs)`
- `cio.ch347(index=0, **kwargs)`
- `cio.start_rpc_server(host="0.0.0.0", port=8000)`

### 5. 单物理底座多路复用（I2C + SPI + GPIO 共用同一串口）

当一块测试底板通过同一个物理串口（如 `COM3`）同时提供 I2C、SPI 与 GPIO 功能时，推荐通过底座的衍生构造器创建逻辑信道：

```python
import cio

# 1. 打开单一物理底座 (物理 Owner)
bridge = cio.connect("serial://COM3?baud=2000000")

# 2. 从底座直接衍生各协议逻辑信道 (借用模式 borrowed=True，底层自动共享串口与事务排他锁)
i2c = bridge.i2c(bus=0, reg_len=2)
gpio = bridge.gpio(pin=1)

with i2c:
    i2c.write_reg(0x57, 0x00, [0x01, 0x02])
# i2c 退出后仅注销自身逻辑状态，底座 bridge 与 gpio 依旧保持正常通信！

gpio.set_high()

# 3. 最终统一关闭物理底座
bridge.close()
```

### 6. 沁恒 CH347 高速 USB 多协议硬件底座与双串口并发

沁恒 CH347 是一颗 USB 2.0 High-Speed（480Mbps）多协议转换芯片。在 Mode 1 / Mode 2 复合功能模式下，同时向操作系统枚举出：
- **双独立高速硬件串口**（如 `COM12`、`COM13`，走标准 CDC / VCP 串口驱动，支持高达 9Mbps+ 波特率）；
- **专有硬件接口**（走 `CH347DLLA64.DLL` / `CH347DLL.DLL` 驱动，支持 1MHz I2C、60MHz SPI 与 8 路 GPIO）。

#### ① 独立端点并发通信契约
两组硬件串口走 USB CDC 独立端点，I2C/SPI/GPIO 走专有 Vendor Bulk 独立端点。**两者的物理信道在芯片内部完全物理隔离**。`carrot-io` 支持在 Python 中开启两个串口进行全双工数据吞吐的同时，并发高速读取 I2C/SPI 传感器，两者零串扰、零相互阻塞。

#### ② CH347 专属调用范式
```python
import cio

# 范式 A：直接使用复合 URL Scheme 打开专有总线（内部自动管理底座句柄生命周期）
with cio.connect("i2c+ch347://0?frequency=400000") as i2c:
    addrs = i2c.scan()                         # 物理总线硬件级 ACK 扫描
    raw = i2c.read_reg(0x44, 0x2400, nbytes=6) # 硬件原子 Repeated-Start 读寄存器

# 范式 B：底座 1 对 N 多路复用借用（I2C + SPI + GPIO 共享同一物理句柄与排他锁）
with cio.ch347(0) as bridge:
    i2c = bridge.i2c(frequency=400000)
    spi = bridge.spi(frequency=15000000, mode=0, cs=0)
    pin = bridge.gpio(pin=3)

    i2c.write(0x44, [0x24, 0x00])
    spi.transfer([0x9F, 0x00, 0x00, 0x00])
    pin.set_high()
```

---

## 二、同步与异步双模调用范式

`carrot-io` 采用 **底层 100% 纯异步核心 + 全局统一同步包装器（`SyncTransportWrapper`）** 的双模同构设计：

### 1. 同步总线阻塞范式（硬件验证与测试推荐）
使用标准 Python `with` 上下文，`dev` **自动返回同步包装视图**，可直接线性调用所有的总线读写方法：

```python
import cio

with cio.connect("i2c+serial://COM3?baud=2000000&reg_len=2&trace=on") as dev:
    # 直接调用同步方法（无需 await，已内置快速路径优化）
    dev.write_reg(0x57, 0xFFB6, 0xFF)
    data = dev.read_reg(0x57, 0xFFB6, nbytes=1)
    print("CP_CTRL readback:", data.hex())
```

### 2. 自动化断言验证范式（结合 `check` / `require` / `verify`）
结合 [cio.check / cio.require](file:///d:/Projects/carrot-io/API.md#四硬件测试与断言框架-ciotestingverify) 使用，提供结构化期望值断言对比、位掩码过滤、现场 Hex Diff 与自动化记分板统计：

```python
from cio import dev, check, require, verify

with dev:
    verify.reset()
    check(dev.read_reg(0x57, 0xFFB1, 1), 0x07, name="STATUS_REG")
    dev.write_reg(0x57, 0xFFB4, 0x03)
    check(dev.read_reg(0x57, 0xFFB4, 1), 0x03, name="REG_FFB4")
    verify.summary()
```

### 3. 原生 Asyncio 异步协程范式（高并发服务/网络网关）
使用 `async with` 上下文，`dev` 为原生异步实例，使用 `await` 调度：

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

### 4. 派生子对象的双模属性转换
所有通道及派生子对象（GPIO `pin`、Protocol `proto`）均支持随时通过 `.sync` 属性切换同步视图：
- **GPIO 引脚**：`pin.sync.set_high()`（同步）/ `await pin.set_high()`（异步）
- **协议绑定**：`proto.sync.write("msg")`（同步）/ `await proto.write("msg")`（异步）
- **底层互转**：`async_dev.sync`（获取同步视图）/ `sync_dev._async`（获取底层原生异步对象）

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
| `dump_history()` | `dev.dump_history(limit=20, color=False, ...) -> str` | 获取格式化后的 TX/RX 通信 Hex 文本流 |
| `bind()` | `dev.bind(codec: BaseCodec) -> ProtocolTransport` | 绑定编解码器生成强类型协议对象 |

#### 通信日志格式化与展示配置 (`dev.logger`)

`dev.logger` 提供了对控制台实时 Trace 与历史 Dump 格式的细粒度控制：

```python
# 1. 属性直读直写
dev.logger.show_hex = False     # 隐藏十六进制原始字节流
dev.logger.show_ascii = False   # 隐藏 ASCII 文本预览
dev.logger.show_time = False    # 隐藏时间戳前缀 [HH:MM:SS.mmm]
dev.logger.show_len = False     # 隐藏字节长度 (XX B)
dev.logger.max_bytes = 32       # 限制单条最大展示字节数（超长自动截断）

# 2. 批量设置
dev.logger.configure(show_hex=False, show_len=False, max_bytes=16)

# 3. 记录自定义诊断/控制事件
dev.logger.log_event("DELAY", "50ms")               # 输出 [EVT] [DELAY ] 50ms
dev.logger.log_event("STATE", "Power rail ON")      # 输出 [EVT] [STATE ] Power rail ON

# 4. 临时覆盖 dump 格式
print(dev.dump_history(limit=10, show_hex=False, show_len=False))
```

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

# 3. I2C 从机设备扫描 (返回 7-bit 地址列表)
addrs = await dev.scan()                                                 # 返回如 [0x50, 0x57]

# 4. 速率配置 (Bridge 专属)
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

针对 UDP Datagram 等有界消息包传输：

```python
async with cio.connect("udp://192.168.1.100:5025") as dev:
    await dev.write(b"PING")
    packet = await dev.read()
    print("Received Packet:", packet)
```



---

## 四、硬件断言与验证子系统 (`check` / `require` / `verify`)

专为硬件寄存器与通信协议测试设计的轻量级断言与计分体系，支持数据归一化（bytes/int/hex str）、硬件位掩码过滤、对齐彩色 Hex Diff 渲染与记分板统计。

### 1. 核心断言接口

| 方法签名 | 说明 | 示例 |
|---|---|---|
| `check(actual, expected, name="", mask=None)` | 软断言（比对失败记录到计分板，不中断流程） | `check(data, "55 AA", name="POR Data")` |
| `require(actual, expected, name="", mask=None)` | 硬断言（关键条件失败立即抛出 `AssertionError`） | `require(dev.read_reg(0x57, 0x00), 0x10)` |
| `check.mask(actual, expected, mask, name="")` | 显式位掩码比对 | `check.mask(reg, 0x10, mask=0x10, name="Bit4")` |
| `require.len(data, expected_len: int, name="")` | 长度断言（通过返回原数据） | `require.len(res, 64, name="Payload Len")` |
| `require.not_none(val, name="")` | 非空断言（通过返回原值） | `card = require.not_none(reader.active())` |
| `check.is_none(val, name="")` | 空值断言 | `check.is_none(err_val, name="No Error")` |
| `require.raises(exc_type, fn, *args, **kwargs)` | 异常捕获断言 | `require.raises(TimeoutError, dev.read)` |
| `verify.summary() -> bool` | 输出格式化汇总记分板 | `sys.exit(0 if verify.summary() else 1)` |

### 2. 多场景使用范式

#### 范式 A：单脚本扁平直跑（默认隐式单例）
```python
from cio import dev, check, require, verify

with dev:
    check(dev.read_reg(0x57, 0xFFB0, 1), 0x10, name="POR Status")
    check(dev.read_reg(0x57, 0x03F0, 16)[14:16], "C8 37", name="Mode Word")
    verify.summary()
```

#### 范式 B：Pytest 单元测试（局部会话隔离）
```python
from cio import dev, check, VerificationSession

def test_eeprom_clear():
    with dev, VerificationSession() as s:
        check(dev.read_reg(0x57, 0x0020, 16), "00" * 16, name="Page 2 Cleared")
        assert s.summary()
```

---

## 五、消息编解码与高层协议 (`cio.core.codec` / `dev.bind`)

通过将任意底层的字节流 Transport 绑定（`dev.bind(codec)`）为强类型 **`ProtocolTransport`**，将底层散装字节收发自动升级为结构化业务对象通道：

### 1. 内置 4 大编解码器 (Built-in Codecs)

```python
from cio.core.codec import LineCodec, FixedLengthCodec, FramedBinaryCodec, StructCodec

# ① 文本行协议 (SCPI 仪器 / NMEA GPS / 文本交互)
proto = dev.bind(LineCodec(delimiter=b"\n", encoding="utf-8"))
resp = await proto.query("*IDN?")  # 自动追加 \n 发送并解析返回字符串
print("仪器型号:", resp)

# ② 定长二进制帧 (固定 N 字节传感器原始报文)
proto = dev.bind(FixedLengthCodec(length=32))
frame = await proto.read()  # 每次精确出队 32 字节完整 bytes

# ③ 经典带头带长工业校验帧: [HEADER 0xAA55][LEN (2B)][PAYLOAD][CRC16]
codec = FramedBinaryCodec(
    header=b"\xAA\x55",
    length_offset=2,
    length_size=2,
    byteorder="big",
    length_includes_header=False,
    crc_type="crc16",  # 支持 "sum8", "xor8", "crc16", 或自定义 Callable 函数
    crc_size=2,
)
proto = dev.bind(codec)
await proto.write(b"\x01\x02\x03")  # 自动组装 [AA 55][00 03][01 02 03][CRC]
payload = await proto.read()         # 自动寻头、校验 CRC、丢弃噪波并返回纯净载荷

# ④ Python Struct 结构体对象 (自动打包/解包元组)
proto = dev.bind(StructCodec(fmt=">HHLL"))
await proto.write((1, 2, 1000, 2000))
data_tuple = await proto.read()     # 直接得到解包后的元组 (1, 2, 1000, 2000)
```

### 2. `ProtocolTransport` 方法与生命周期契约

| 方法签名 | 说明 | 示例 |
|---|---|---|
| `await proto.write(message, timeout=None) -> int` | 将结构化对象编码为 bytes 并发送 | `await proto.write("MEAS:VOLT?")` |
| `await proto.read(timeout=None) -> Any` | 从底层缓冲接收并解码返回单个业务对象 | `data = await proto.read()` |
| `await proto.query(message, delay=0.0, timeout=None) -> Any` | 发送业务对象并在延时后读取解析响应 | `res = await proto.query("*IDN?")` |
| `await proto.flush() -> None` | 清空编解码残余缓冲区与底层流 | `await proto.flush()` |
| `proto.dump_history(limit=20, ...) -> str` | 渲染最近的原始帧通信历史 | `print(proto.dump_history(limit=5))` |
| `with proto as p:` | 同步上下文管理器（非 async 代码阻塞调用） | `p.write("PING"); msg = p.read()` |
| `async with proto as p:` | 异步原生上下文管理器 | `async with proto as p: ...` |

### 3. 自定义私有协议 Codec 扩展模板

只需继承 `BaseCodec` 实现 `encode` 和 `decode` 两个纯函数方法：

```python
from cio.core.codec import BaseCodec

class CustomTLVCodec(BaseCodec):
    """自定义 TLV 协议: [TAG 1B][LEN 1B][VALUE]"""
    
    def encode(self, message: tuple[int, bytes]) -> bytes:
        tag, val = message
        return bytes([tag, len(val)]) + val

    def decode(self, buffer: bytearray) -> tuple[tuple[int, bytes] | None, int]:
        if len(buffer) < 2:
            return None, 0  # 字节不足，返回 (None, 0) 等待后续数据
        tag = buffer[0]
        length = buffer[1]
        total_len = 2 + length
        if len(buffer) < total_len:
            return None, 0
        value = bytes(buffer[2:total_len])
        return (tag, value), total_len  # 成功解析并消费 total_len 字节
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
所有写入入参均声明为 `BytesLike = bytes | bytearray | int | list[int] | tuple[int, ...]，内部通过 `cio.ensure_bytes()` 统一归一化：
- `dev.write(b"\x01\x02")`
- `dev.write([0x01, 0x02, 0x03])`
- `dev.write((0x01, 0x02))`
- `dev.write(0xFF)` （自动识别为 `b"\xFF"`）

### 2. 异常继承树 (`cio.core.exceptions`)
```text
TransportError (基类)
 ├── DriverMissingError (驱动或物理依赖缺失)
 │    ├── PythonPackageMissingError (缺少 pyserial / pyftdi 等 pip 包)
 │    └── CDllMissingError (缺少 visa32.dll 等 C 动态链接库)
 ├── ConnectionError (连接建立失败)
 │    ├── ConnectTimeoutError (连接超时)
 │    └── ConnectionRefusedError (连接被拒绝)
 ├── IOOperationError (读写 I/O 操作失败)
 │    ├── ReadTimeoutError (读取超时 / read_until 未匹配)
 │    ├── WriteTimeoutError (写入超时)
 │    ├── BufferOverflowError (缓冲区溢出)
 │    ├── WriteError (写入失败)
 │    └── FrameChecksumError (帧校验 CRC/CheckSum 错误)
 └── InvalidUrlError (URL Scheme 或参数格式错误)
```


---

## 八、即拷即用标准代码模板 (Recipes)

### 模板 1：I2C 芯片寄存器自动化验证 (同步 check / verify 范式)
```python
from __future__ import annotations
import sys
import time
from cio import dev, check, require, verify

I2C_ADDR = 0x57

def verify_chip() -> bool:
    with dev:
        verify.reset()

        # 1. 状态寄存器校验
        check(dev.read_reg(I2C_ADDR, 0xFFB1, 1), 0x07, name="STATUS_REG")
        check(dev.read_reg(I2C_ADDR, 0xFFB0, 1), 0x10, name="STATUS")

        # 2. 寄存器写入与回读校验
        dev.write_reg(I2C_ADDR, 0xFFB4, 0x03)
        check(dev.read_reg(I2C_ADDR, 0xFFB4, 1), 0x03, name="REG_FFB4")

        # 3. EEPROM 页写入与回读校验
        test_payload = [0x55] * 16
        dev.write_reg(I2C_ADDR, 0x0020, test_payload)
        time.sleep(0.05)  # 等待 EEPROM 烧写
        check(dev.read_reg(I2C_ADDR, 0x0020, 16), test_payload, name="EEPROM 0x0020")

        return verify.summary()

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

### 模板 4：沁恒 CH347 高速 I2C 传感器采集与双串口并发通信
```python
import asyncio
import cio

async def main():
    # 1. 打开 CH347 硬件 I2C
    i2c = cio.connect("i2c+ch347://0?frequency=400000")
    await i2c.open()

    # 扫描总线在线从机 (精准过滤空地址)
    devices = await i2c.scan()
    print("Online I2C devices:", [hex(a) for a in devices])

    # 2. 读取 SHT30 温湿度传感器 (触发高精度测量命令 0x2400，读取 6 字节数据)
    await i2c.write(0x44, [0x24, 0x00])
    await asyncio.sleep(0.05)  # 等待传感器 ADC 转换
    raw = await i2c.read(0x44, 6)

    temp_raw = (raw[0] << 8) | raw[1]
    humi_raw = (raw[3] << 8) | raw[4]
    temp = -45 + 175 * (temp_raw / 65535.0)
    humi = 100 * (humi_raw / 65535.0)
    print(f"SHT30 Temperature: {temp:.2f} °C, Humidity: {humi:.2f} %RH")

    # 3. 此时双串口（如 COM12 与 COM13）可同时进行全双工收发，零相互阻塞
    async with cio.connect("serial://COM12?baud=115200") as u1, \
               cio.connect("serial://COM13?baud=115200") as u2:
        await u1.write(b"HELLO_CH347_UART")
        echo = await u2.read_exact(16)
        print("UART Loopback Echo:", echo)

    await i2c.close()

if __name__ == "__main__":
    asyncio.run(main())
```
