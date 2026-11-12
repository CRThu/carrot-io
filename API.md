# carrot-io (cio) API 参考与开发者速查手册

本文档为 `carrot-io`（Python 导入包名：`cio`）的**权威 API 参考与代码实战速查手册**。为 AI Agent 与自动化测试工程师提供开箱即用的接口契约、参数说明与标准代码模板。

---

## 目录

- [一、顶层入口与连接工厂 (`cio.connect`)](#一顶层入口与连接工厂-cioconnect)
  - [1. 硬件定位器语法全景表](#1-cioconnectlocator-str-kwargs---asyncbasetransport--asyncbasebus)
  - [2. 协议桥注册与扩展 (`cio.register_bridge`)](#2-协议桥注册与扩展-cioregister_bridge)
  - [3. `cio.scan` 设备静默探测](#3-cioscankind-str--none--none---listdict)
  - [4. 极简 DSL 单例与环境变量注入 (`from cio import dev`)](#4-极简-dsl-单例与环境变量注入-from-cio-import-dev)
  - [5. 快捷构造函数](#5-快捷构造函数)
  - [6. 单物理底座多路复用（I2C + SPI + GPIO 共用同一串口）](#6-单物理底座多路复用i2c--spi--gpio-共用同一串口)
  - [7. 沁恒 CH347 高速 USB 多协议硬件底座与双串口并发](#7-沁恒-ch347-高速-usb-多协议硬件底座与双串口并发)
- [二、同步与异步双模调用范式](#二同步与异步双模调用范式)
- [三、总线传输契约与接口方法](#三总线传输契约与接口方法)
  - [1. 基础传输接口 (`AsyncBaseTransport` / `SyncTransportWrapper`)](#1-基础传输接口-asyncbasetransport--synctransportwrapper)
  - [2. 字节流传输 (`AsyncStreamTransport` / `AsyncUartTransport`)](#2-字节流传输-asyncstreamtransport--asyncuarttransport)
  - [3. I2C 主机总线 (`AsyncI2cBus` / `AsyncI2cBridge`)](#3-i2c-主机总线-asynci2cbus--asynci2cbridge)
  - [4. SPI 全双工总线 (`AsyncSpiBus` / `AsyncSpiBridge`)](#4-spi-全双工总线-asyncspibus--asyncspibridge)
  - [5. GPIO 引脚控制 (`AsyncGpioBus` / `AsyncGpioBridge`)](#5-gpio-引脚控制-asyncgpiobus--asyncgpiobridge)
  - [6. UDP 与离散报文传输体系 (`UdpTransport` / `AsyncPacketTransport`)](#6-udp-与离散报文传输体系-udptransport--asyncpackettransport)
  - [7. 工业仪器与 VISA 传输体系 (`VisaTransport`)](#7-工业仪器与-visa-传输体系-visatransport)
- [四、硬件断言与验证子系统 (`check` / `require` / `verify`)](#四硬件断言与验证子系统-check--require--verify)
- [五、消息编解码与高层协议 (`cio.protocols` / `dev.bind`)](#五消息编解码与高层协议-cioprotocols--devbind)
- [六、高层设备与工业仪器门面 (`cio.devices`)](#六高层设备与工业仪器门面-ciodevices)
- [七、远程 RPC 硬件代理网关 (`cio.composite.rpc`)](#七远程-rpc-硬件代理网关-ciocompositerpc)
- [八、多通道时序数据收集器 (`cio.Collector`)](#八多通道时序数据收集器-ciocollector)
- [九、数据类型与异常体系](#九数据类型与异常体系)
- [十、即拷即用标准代码模板 (Recipes)](#十即拷即用标准代码模板-recipes)

---

## 一、顶层入口与连接工厂 (`cio.connect`)

### 1. `cio.connect(locator: str, **kwargs) -> AsyncBaseTransport | AsyncBaseBus`
统一硬件定位器工厂函数。基于分层定位器语法（Layered Locator Grammar）自动解析并实例化底层驱动与协议桥，摒弃生硬的 Web URL 格式。

#### 硬件定位器语法全景表

**标准语法契约**：
`[bus[bridge]:[channel][,k=v...] @] transport:[target][,k=v...]`

| 类型 | 定位器示例 | 说明与常用参数 |
|---|---|---|
| **原生串口** | `serial:COM3,baud=115200` | PySerial 串口，参数：`baud=`, `parity=N/E/O`, `stopbits=1/2`, `bytesize=8`, `timeout=1.0` |
| **原生 TCP** | `tcp:192.168.1.100:5025` | 异步 TCP Socket 流，参数：`timeout=2.0`, `buffer_size=16MB` |
| **原生 UDP** | `udp:192.168.1.100:5025` | 异步 UDP 流式 Socket（已归一为流，支持 `read_until`），参数：`timeout=2.0`, `buffer_size=16MB` |
| **FTDI 控制器** | `ftdi:ftdi:232h/1,baud=115200` | PyFTDI 适配器 |
| **CH347 底座** | `ch347:0` | 沁恒 CH347 高速多协议底座，参数：`index=0` |
| **I2C 协议桥 (串口)** | `i2c[cb]:0,reg_len=2 @ serial:COM3,baud=2000000` | 串口底座挂接 CarrotBridge I2C 主机，参数：`reg_len=1/2/4`, `speed=` |
| **CH347 原生 I2C** | `i2c:0,frequency=400000 @ ch347:0` | 显式指定 CH347 硬件原生 I2C 主机（原生硬件无需桥），参数：`frequency=`, `reg_len=1/2/4` |
| **SPI 全双工 (串口)** | `spi[cb]:0,cs=0 @ serial:COM3,baud=2000000` | 串口底座挂接 CarrotBridge SPI 主机，参数：`cs=0`, `bus=0` |
| **SPI (网络桥)** | `spi[cb]:0,clock=10MHz @ tcp:192.168.1.100:5025` | 显式指定 TCP 底座并挂接 SPI 协议桥 |
| **CH347 原生 SPI** | `spi:0,frequency=15000000,mode=0,cs=0 @ ch347:0` | 显式指定 CH347 硬件原生 SPI 主机（原生硬件无需桥），参数：`frequency=`, `mode=0/1/2/3`, `cs=0/1` |
| **GPIO 引脚控制** | `gpio[cb]:1 @ serial:COM3,baud=2000000` | 串口底座挂接 CarrotBridge GPIO 引脚控制 |
| **CH347 原生 GPIO**| `gpio:3 @ ch347:0` | 显式指定 CH347 硬件原生 GPIO 引脚控制（原生硬件无需桥），参数：`pin=0~7` |
| **VISA 仪器设备** | `visa:USB0::0x2A8D::0x9007::MY63160152::INSTR,timeout=5.0` | PyVISA 仪表（示波器/万用表/信号源/GPIB/VXI），参数：`timeout=5.0`, `encoding=ascii`, `read_termination=`, `backend=@ni` |
| **外挂协议桥** | `i2c[nc]:0,reg_len=2 @ serial:COM5,baud=2000000` | 方括号显式指定协议桥（支持 `cb`、外挂别名 `nc` 或内联 `module:Class`） |
| **RPC 硬件代理** | `rpc:192.168.1.50:8000/COM1,baud=115200` | 跨网络机器远程硬件透明代理 |

> **分层硬件定位器设计哲学：**
> - **单 `@` 物理隔离边界**：以 `@` 分界，左侧为高层应用协议/总线逻辑（`i2c[cb]:0,reg_len=2`），右侧为物理传输链路（`serial:COM3,baud=2000000`）；
> - **显式协议桥契约**：对于原生具备总线能力的硬件（如 `ch347:0`），直接直通；对于生肉字节流信道（`serial` / `tcp`），必须显式指明协议桥（如 `i2c[cb]:0` 或 `i2c[nc]:0`），或通过 `.env` 中的 `CIO_DEFAULT_BRIDGE_I2C` 声明默认桥，彻底告别隐式协议假设；
> - **Python 运算符重载与类直传**：支持 `bus = cio.i2c["cb"](0) @ cio.serial(...)`，亦支持直传协议桥类 `bus = cio.i2c[MyBridgeClass](0) @ cio.serial(...)`；
> - **通用定位器参数：**
>   - `trace=on` / `trace=off`：开启或关闭控制台通信实时 Trace 打印（支持 `on/off`, `1/0`, `true/false`）。
>   - `bridge_trace=on`：在协议桥层（如 CarrotBridge）开启对下位机底层 ASCII 命令帧（`[CMD]` / `[RETURN]`）的追踪。
>   - `show.ascii=0/1`：控制是否展示 ASCII 字符预览列（常用于 EEPROM/二进制测试隐藏乱码字符，如 `show.ascii=0`）。
>   - `show.hex=0/1`：控制是否展示十六进制原始字节列。
>   - `show.time=0/1`：控制是否展示时间戳前缀 `[HH:MM:SS.mmm]`。
>   - `show.len=0/1`：控制是否展示字节长度标签 `(XX B)`。
>   - `show.color=0/1`：强制开启或关闭控制台 ANSI 着色渲染。
>   - `max_bytes=N`：单条追踪记录最大截断展示字节数（默认 `64`）。
>   - `timeout=2.0`：统一设置默认 I/O 超时（秒），默认全库生效防挂死，支持显式传参或 `timeout=None` 覆盖。
>   - `buffer_size=16777216`：流传输（Serial / TCP / UDP / VISA / FTDI）默认统一配备 16MB 动态安全缓冲区，零内存空耗。

### 2. 协议桥注册、类对象直传与环境变量外挂 (`cio.register_bridge`)

`cio` 彻底解耦了总线抽象与协议桥，支持以下三种灵活外挂协议桥的形态：

#### 方式一：类装饰器 / 函数式注册
```python
import cio
from cio import AsyncI2cBus, AsyncBaseTransport

# 装饰器注册：直接挂载到总线命名空间
@cio.register_bridge("i2c", ["nc", "nc_bridge"])
class NcI2cBridge(AsyncI2cBus):
    def __init__(self, transport: AsyncBaseTransport, reg_len: int = 2, **kwargs):
        super().__init__(reg_len=reg_len, **kwargs)
        self.transport = transport
        # 自定义二进制协议帧编解码逻辑...

# 即插即用连接 (通过 [nc] 语法指定)
dev = cio.connect("i2c[nc]:0,reg_len=2 @ serial:COM5,baud=2000000")
```

#### 方式二：类对象第一等公民直接传入（无需注册别名）
```python
# 1. 配合 Python @ 运算符直传类
dev = cio.i2c[NcI2cBridge](0, reg_len=2) @ cio.serial("COM5", baud=2000000)

# 2. 或配合 connect() 显式参数覆盖
dev = cio.connect("i2c:0,reg_len=2 @ serial:COM5,baud=2000000", bridge=NcI2cBridge)
```

#### 方式三：零代码侵入：`.env` 环境变量外挂声明（最适合 CI/自动化测试）
在 `.env` 或系统环境变量中配置对应的桥类模块路径，测试脚本中直接读取 `cio.dev`：

```bash
# .env 配置文件
CIO_DEVICE="i2c[nc]:0,reg_len=2 @ serial:COM5,baud=2000000"

# 外挂桥类映射 (格式：CIO_BRIDGE_{NAME}="module_name:ClassName")
CIO_BRIDGE_NC="controller_bridge:NcI2cBridge"
```

```python
# 测试脚本无需显式 import 和注册桥，开箱即用：
from cio import dev

with dev:
    dev.read_reg(0x57, 0xFFB0)  # 自动走 NC 桥二进制收发，且享有 Trace 和历史记录
```

> 💡 **内联模块语法**：定位器亦支持直接内联指定模块类路径，如 `connect("i2c[my_pkg.bridge:CustomBridge]:0 @ serial:COM5")`。

### 3. `cio.scan(kind: str | None = None) -> list[dict]`
静默探测系统当前可用的物理硬件与串口设备，无可用设备时静默返回空列表。

### 4. 极简 DSL 单例与环境变量注入 (`from cio import dev`)

为支持极简测试脚本与领域特定语言（DSL）调用，`cio` 提供开箱即用的模块级惰性单例 `dev` 与本级目录 `.env` 环境变量注入：

```bash
# 当前工作目录下的 .env
CIO_DEVICE="i2c[cb]:0,reg_len=2 @ serial:COM3,baud=2000000"
CIO_DEVICE_POWER="serial:COM4,baud=9600"
```

```python
# 01_ee_clear.py —— 无需 with，无需显式 connect，开箱即用
from cio import dev

# 1. 默认设备操作 (读取 CIO_DEVICE)
dev.write_reg(0x57, 0xFFB6, 0xFF)
data = dev.read_reg(0x57, 0xFFB0, 1)

# 2. 具名多设备下标访问 (读取 CIO_DEVICE_POWER)
dev["power"].write("VSET 3.3\n")

# 3. 主动清理历史与连接复位
dev.clear_history()             # 清空当前设备内存追踪日志
dev.close()                     # 关闭设备并从全局池注销，便于重置重连
cio.close_all_devices()         # 批量回收关闭所有单例
```

> **安全与生命周期保障：**
> - **惰性连接**：`from cio import dev` 在导入阶段零副作用，只有首次调用方法时才建立硬件连接。
> - **`atexit` 自动安全回收**：脚本正常结束或异常崩溃退出时，底层自动安全关闭串口与物理连接，彻底杜绝操作系统端口死锁。
> - **状态守恒**：`dev.close()` 与 `cio.close_device()` 显式关闭设备后自动从缓存池注销，重新调用立即透明创建全新干净连接。

### 5. 快捷构造函数
- `cio.serial(port="COM1", baud=115200, timeout=2.0, buffer_size=16MB, **kwargs)`
- `cio.tcp(host="127.0.0.1", port=5025, timeout=2.0, buffer_size=16MB, **kwargs)`
- `cio.udp(host="127.0.0.1", port=5025, timeout=2.0, buffer_size=16MB, **kwargs)`（已升级为流式传输，完整支持按行读取）
- `cio.ftdi(url="ftdi://ftdi:232h/1", baud=115200, timeout=2.0, buffer_size=16MB, **kwargs)`
- `cio.ch347(index=0, timeout=2.0, buffer_size=16MB, **kwargs)`
- `cio.visa(resource_name, timeout=5.0, encoding="ascii", buffer_size=16MB, **kwargs)`
- `cio.start_rpc_server(host="0.0.0.0", port=8000)`

### 6. 单物理底座多路复用（I2C + SPI + GPIO 共用同一串口）

当一块测试底板通过同一个物理串口（如 `COM3`）同时提供 I2C、SPI 与 GPIO 功能时，推荐通过底座的衍生构造器创建逻辑信道：

```python
import cio

# 1. 打开单一物理底座 (物理 Owner)
bridge = cio.connect("serial:COM3,baud=2000000")

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

### 7. 沁恒 CH347 高速 USB 多协议硬件底座与双串口并发

沁恒 CH347 是一颗 USB 2.0 High-Speed（480Mbps）多协议转换芯片。在 Mode 1 / Mode 2 复合功能模式下，同时向操作系统枚举出：
- **双独立高速硬件串口**（如 `COM12`、`COM13`，走标准 CDC / VCP 串口驱动，支持高达 9Mbps+ 波特率）；
- **专有硬件接口**（走 `CH347DLLA64.DLL` / `CH347DLL.DLL` 驱动，支持 1MHz I2C、60MHz SPI 与 8 路 GPIO）。

#### ① 独立端点并发通信契约
两组硬件串口走 USB CDC 独立端点，I2C/SPI/GPIO 走专有 Vendor Bulk 独立端点。**两者的物理信道在芯片内部完全物理隔离**。`carrot-io` 支持在 Python 中开启两个串口进行全双工数据吞吐的同时，并发高速读取 I2C/SPI 传感器，两者零串扰、零相互阻塞。

#### ② CH347 专属调用范式
```python
import cio

# 范式 A：直接使用分层定位器打开专有总线（内部自动管理底座句柄生命周期）
with cio.connect("i2c:0,frequency=400000 @ ch347:0") as i2c:
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

with cio.connect("i2c[cb]:0,reg_len=2,trace=on @ serial:COM3,baud=2000000") as dev:
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
    async with cio.connect("i2c[cb]:0,reg_len=2,trace=on @ serial:COM3,baud=2000000") as dev:
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
| `capabilities` | `dev.capabilities -> frozenset[str]` | 显式能力契约声明（如 `{"stream", "uart"}` 或 `{"i2c", "spi", "gpio"}`） |
| `flush()` | `dev.flush()` | 清空内部接收缓冲区 |
| `history()` | `dev.history(limit=100) -> list[TraceEntry]` | 获取内存中的历史收发追溯条目 |
| `dump_history()` | `dev.dump_history(limit=20, color=False) -> str` | 获取格式化后的 TX/RX 跟踪文本流 |
| `bind()` | `dev.bind(codec: BaseCodec) -> ProtocolTransport` | 绑定编解码器生成强类型协议对象 |

#### 通信追踪体系与分层透视 (`dev.trace` / `dev.trace.show`)

`cio` 采用严格分层的通信追踪模型，在不同抽象层级提供对应的追踪视角：

##### 1. 三层追踪架构与输出对比

| 追踪层级 | 开启方式 | 核心标签 | 关注内容与格式示例 |
|---|---|---|---|
| **逻辑总线层** | `i2c[cb]:...,trace=on` | `[I2C]` / `[SPI]` / `[GPIO]` | **业务总线原子事务**（地址、寄存器、读写有效载荷，隐藏中间写地址操作）：<br>`[12:00:00.000] [I2C] RD 0x57 @ 0xFFB0      <- 10 (1B)`<br>`[12:00:00.005] [I2C] WR 0x57 @ 0xFFE6      -> 55 (1B)`<br>`[12:00:00.010] [I2C] SCAN                  <- [0x57] (Found 1)` |
| **协议桥网关层** | `i2c[cb]:...,bridge_trace=on` | `[CMD]` / `[RETURN]` / `[MSG]` | **下位机固件 ASCII 交互**（指令下发、标准回包、异步日志）：<br>`[12:00:00.000] [CMD]    -> IIC.W(0x57, 0xFFB0, 2) (23B)`<br>`[12:00:00.001] [RETURN] <- [RETURN]: 2 (13B)`<br>`[12:00:00.002] [CMD]    -> IIC.R(0x57, 1) (15B)`<br>`[12:00:00.003] [RETURN] <- [RETURN]: 0x10 (16B)` |
| **物理信道层** | `serial:...,trace=on` | `[TX]` / `[RX]` | **原始字节流收发**（十六进制 Hex Dump、ASCII 预览与字节数）：<br>`[12:00:00.015] [TX] -> 48 45 4C 4C 4F (5B) \| HELLO`<br>`[12:00:00.018] [RX] <- 57 4F 52 4C 44 (5B) \| WORLD` |

##### 2. 追踪展示控制器 (`dev.trace.show`)

`dev.trace` 提供了对控制台实时 Trace 与历史 Dump 格式的结构化控制器 `trace.show`，支持**定位器单点内联声明**与**代码动态点选**两种方式：

```dotenv
# 推荐实践：在 .env 硬件定位器中单点声明展示参数（全局所有测试脚本免写代码，零样板侵入）：
CIO_DEVICE="i2c[cb]:0,reg_len=2,trace=on,show.ascii=0 @ serial:COM3,baud=2000000"
```

```python
# 亦可在代码中动态点选配置：
# 1. 结构化属性点选控制
dev.trace.show.hex = False       # 隐藏十六进制原始字节流
dev.trace.show.ascii = False     # 隐藏 ASCII 文本预览（EEPROM/二进制测试推荐）
dev.trace.show.time = False      # 隐藏时间戳前缀 [HH:MM:SS.mmm]
dev.trace.show.len = False       # 隐藏字节长度 (XX B)
dev.trace.show.color = False     # 强制关闭 ANSI 着色
dev.trace.show.max_bytes = 32    # 限制单条最大展示字节数（超长自动截断）

# 2. 批量函数式链式调用
dev.trace.show(ascii=False, len=False, max_bytes=16)

# 3. 调取历史转储（用于异常上报与日志持久化）
print(dev.dump_history(limit=10))
```

---

### 2. 字节流传输 (`AsyncStreamTransport` / `AsyncUartTransport`)

针对 TCP、UDP、Serial 串口、FTDI UART、CH347 及 VISA 仪表等所有流式通道提供高级流操作（全库统一默认 2.0s 超时、VISA 仪表统一默认 5.0s 超时与 16MB 动态安全缓冲区）：

```python
# 同步调用
data = dev.read_exact(16)            # 精确读取 16 字节，不足则等待直到超时
line = dev.read_until("\n")          # 读取直到遇到指定分隔符（支持 "\n" 字符串或 b"\n" 原始字节）
dev.flush()                          # 清空 FifoBuffer 缓冲数据

# 异步调用 (加 await)
data = await dev.read_exact(16)
line = await dev.read_until("\r\n", timeout=1.0)
```

---

### 3. I2C 主机总线 (`AsyncI2cBus` / `AsyncI2cBridge`)

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

### 4. SPI 全双工总线 (`AsyncSpiBus` / `AsyncSpiBridge`)

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

### 5. GPIO 引脚控制 (`AsyncGpioBus` / `AsyncGpioBridge`)

引脚级电平与边沿控制契约：

```python
pin = cio.connect("gpio[cb]:1 @ serial:COM3")

await pin.set_high()                                                     # 输出高电平
await pin.set_low()                                                      # 输出低电平
await pin.toggle()                                                       # 翻转电平
level = await pin.read_level()                                           # 读取当前电平 (True/False)
await pin.config_mode("OUT,PP")                                          # 配置模式: "IN", "OUT,PP", "OUT,OD"
await pin.config_pull("UP")                                              # 配置上下拉: "NONE", "UP", "DOWN"
is_triggered = await pin.wait_for_edge(edge="rising", timeout=2.0)       # 等待上升沿 ("rising", "falling", "both")
```

---

### 6. UDP 与离散报文传输体系 (`UdpTransport` / `AsyncPacketTransport`)

#### ① UDP 原生流式化 (`UdpTransport -> AsyncStreamTransport`)
在 `carrot-io` 中，UDP 传输通道已全面升级归一为标准的 **`AsyncStreamTransport`**。底层收到的每一个 UDP 数据报有效载荷将自动流入 `FifoBuffer`，支持完整的流式操作（按行截取、按长度截取、原子问答）：

```python
# 1. 像操作 TCP / 串口一样使用 UDP，支持任意换行符切分与问答
async with cio.connect("udp:192.168.1.100:5025") as dev:
    await dev.write(b"*IDN?\n")
    response_line = await dev.read_until(b"\n", timeout=2.0)
    print("UDP Reply:", response_line)

# 2. 快捷构造与同步范式
with cio.udp("192.168.1.100", 5025, timeout=2.0) as dev:
    dev.write(b"VOLT:MEAS?\n")
    print("Voltage:", dev.read_until(b"\n"))
```

#### ② 专有离散报文包基类 (`AsyncPacketTransport`)
针对 CANbus 帧、遥测广播等不可流式化的非文本离散报文，可基于 `AsyncPacketTransport` 实现，支持 `DEFAULT_PACKET_QUEUE_SIZE = 1024` 的安全队列深度控制。

---

### 7. 工业仪器与 VISA 传输体系 (`VisaTransport`)

针对 USB-TMC、GPIB、VXI、以太网 SCPI 仪器（示波器、静电计、万用表、信号源等）提供专有物理流封装。兼容系统安装的 **NI-VISA**、**Keysight VISA** 运行库或纯 Python 后端（`PyVISA-py`）。

#### ① 显式能力声明与工业默认参数
- **支持前缀**：`visa:`、`gpib:`、`vxi:`
- **能力集合**：`capabilities = frozenset({"stream", "visa"})`
- **默认超时**：统一为工业仪表专用的 **`5.0s`**（普通流为 2.0s）
- **默认编码**：严格遵循 SCPI / IEEE 488.2 物理标准的 **7-bit ASCII**（`encoding="ascii"`），在发送端就地拦截中文全角标点等非法字符（抛出 `UnicodeEncodeError`），杜绝脏数据进入总线队列

#### ② 定位器与参数配置表

| 定位器参数 | 默认值 | 说明与示例 |
|---|---|---|
| `timeout` | `5.0` | 通信与查询超时时间（秒）：`timeout=5.0` |
| `encoding` | `"ascii"` | SCPI 文本编解码格式，支持自定义覆盖：`encoding=utf-8`、`encoding=latin-1` |
| `read_termination` | `None` | 读取定界符（USBTMC/GPIB 依赖硬件 EOI 信号；串口 ASRL / Socket 仪器推荐设为 `\n`） |
| `write_termination`| `None` | 写入定界符（字符串写入未以此结尾时自动补齐换行，默认 `\n`） |
| `backend` | `None` | 显式指定 VISA 运行时后端：`backend=@ni`、`backend=@keysight` 或 `backend=@py` |
| `chunk_size` | `4096` | 每次物理切片读取缓冲区大小（字节） |
| `buffer_size` | `16MB` | 软件 FIFO 环形缓冲区上限 |

#### ③ 核心方法与 SCPI 交互契约

| 方法签名 | 说明 | 示例 |
|---|---|---|
| `query(cmd, delay=0.0, timeout=None)` | **原子问答事务**：发送前自动排空残余 FIFO 缓冲（杜绝回包错位），等待后回读。<br>若 `cmd` 为 `str`，按 `encoding` 解码并剔除末尾 `\r\n` 返回字符串；若为 `bytes`，直接返回原始字节。 | `idn = inst.query("*IDN?")`<br>`val = float(inst.query(":MEAS:CURR?"))` |
| `query_raw(cmd, delay=0.0, timeout=None) -> bytes` | **二进制无损读取**：专为示波器波形（`:WAV:DATA?`）、内部寄存器 dump 设计。无论 `cmd` 传文本还是字节，一律返回纯原始 `bytes`，绝不触发字符解码破坏波形。 | `raw_bytes = inst.query_raw(":WAV:DATA?")` |
| `write(data, timeout=None) -> int` | 发送 SCPI 指令或原始数据。若 `data` 为 `str`，自动补齐换行并通过 `encoding` 编码为字节后发送。 | `inst.write("*RST")`<br>`inst.write(":CHAN1:DISP ON")` |
| `clear() -> None` / `flush() -> None` | **软硬件同步复位**：触发 VISA `viClear()` 硬件总线复位清除仪器队列，并**同步排空内部软件 FIFO 缓冲**，确保状态机绝对干净。 | `inst.clear()` / `inst.flush()` |
| `read(nbytes=-1)` / `read_until(delimiter)` | 基础流读取（`read_until` 兼容 `"\n"` 或 `b"\n"`）。 | `line = inst.read_until("\n")` |

#### ④ 调用范式示例

```python
import cio

# 1. 快捷工厂函数直连（同步范式）
with cio.visa("USB0::0x2A8D::0x9A01::MY61390950::INSTR", timeout=5.0) as inst:
    print("设备标识:", inst.query("*IDN?"))
    inst.write(":SENS:CURR:RANG:AUTO ON")

    # 标量量测读取
    current = float(inst.query(":MEAS:CURR?"))
    print(f"当前电流: {current:.3e} A")

    # 读取原始二进制波形数据（使用 query_raw）
    raw_waveform = inst.query_raw(":WAV:DATA?")
    print(f"读取波形字节数: {len(raw_waveform)}")

# 2. 原生协程异步范式
async def run():
    async with cio.connect("visa:USB0::0x2A8D::0x9A01::MY61390950::INSTR,encoding=ascii") as inst:
        idn = await inst.query("*IDN?")
        raw = await inst.query_raw(":WAV:DATA?")
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

## 五、消息编解码与高层协议 (`cio.protocols` / `dev.bind`)

通过将任意底层的字节流 Transport 绑定（`dev.bind(codec)`）为强类型 **`ProtocolTransport`**，将底层散装字节收发自动升级为结构化业务对象通道：

### 1. 内置 4 大编解码器 (Built-in Codecs)

```python
from cio import LineCodec, FixedLengthCodec, FramedBinaryCodec, StructCodec

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
from cio import BaseCodec

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

## 六、高层设备与工业仪器门面 (`cio.devices`)

为提升业务脚本的开发体验，`carrot-io` 在基础流与总线传输之上提供了面向对象的厂商设备门面层：
- **`BaseScpiDevice` / `BaseVisaDevice`**：工业仪器与 SCPI 设备基类，提供 IEEE 488.2 标准通用指令与自诊断方法；
- **`keysight.B2985`**：Keysight B2980 系列高精度静电计 / 高阻计专属驱动。

### 1. 接入与调用范式

#### 方式 A：厂商命名空间直调（推荐，最自然直观）
```python
import cio
from cio.devices import keysight

# 传入底层打开的传输链路（VISA / TCP / Serial）
with cio.visa("USB0::0x2A8D::0x9A01::MY61390950::INSTR") as inst:
    with keysight.B2985(inst) as smu:
        print("设备标识:", smu.idn())
        print("微弱电流:", smu.measure_current(), "A")
        print("高阻测量:", smu.measure_resistance(), "Ω")
```

#### 方式 B：单行定位器便捷调用（自管理底层生命周期）
```python
from cio.devices import keysight

with keysight.B2985("visa:USB0::0x2A8D::0x9A01::MY61390950::INSTR") as smu:
    smu.source_voltage(1.0, output=True, protection=True)
    curr = smu.measure_current()
```

#### 方式 C：原生协程纯异步范式
```python
from cio.devices import keysight

async with keysight.B2985("visa:USB0::0x2A8D::0x9A01::MY61390950::INSTR") as smu:
    curr = await smu.measure_current()
    errs = await smu.errors()
```

### 2. `keysight.B2985` 常用接口清单

| 方法签名 | 说明 | 示例 |
|---|---|---|
| `measure_current() -> float` | 测量电流（A，自动清洗 9.91E37 溢出值为 NaN） | `curr = smu.measure_current()` |
| `measure_voltage() -> float` | 测量电压（V） | `volt = smu.measure_voltage()` |
| `measure_resistance() -> float` | 测量高阻阻值（Ω，支持至 10 PΩ） | `res = smu.measure_resistance()` |
| `measure_charge() -> float` | 测量电荷量（C） | `char = smu.measure_charge()` |
| `measure() -> float` | 单次触发并返回当前主测量单值 | `val = smu.measure()` |
| `set_auto_range(enable=True, func="CURR")` | 配置自动量程开关 | `smu.set_auto_range(True)` |
| `set_nplc(nplc=1.0, func="CURR")` | 设置积分时间滤波周期（0.001 ~ 100 PLC） | `smu.set_nplc(1.0)` |
| `set_zero_correct(enable=True)` | 开启/关闭微弱电流零点校准 | `smu.set_zero_correct(True)` |
| `source_voltage(volts, output=None, protection=None)` | 设置电压源电压（可一键配置 output 开关与 20MΩ 保护电阻） | `smu.source_voltage(1.0, output=True, protection=True)` |
| `get_source_voltage() -> float` | 查询当前电压源设定值 | `v_set = smu.get_source_voltage()` |
| `set_output(enable: bool)` | 开启或关闭电压源输出开关 | `smu.set_output(True)` |
| `get_output() -> bool` | 查询当前输出开关状态 | `if smu.get_output(): ...` |
| `set_protection(enable=True)` | 开启/关闭 20 MΩ 串联安全保护电阻 (RLIM) | `smu.set_protection(True)` |
| `get_protection() -> bool` | 查询 20 MΩ 限流保护电阻开关状态 | `is_prot = smu.get_protection()` |
| `idn() -> str` | 查询仪器识别标识符 (`*IDN?`) | `print(smu.idn())` |
| `reset()` | 复位仪器出厂设定 (`*RST`) | `smu.reset()` |
| `clear()` | 清空缓冲区与复位状态 | `smu.clear()` |
| `errors() -> list[str]` | 读取并清空系统错误队列 (`:SYST:ERR?`) | `assert smu.errors() == []` |


---

## 七、远程 RPC 硬件代理网关 (`cio.composite.rpc`)

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

# 定位器格式: rpc:<RPC服务器IP>:<RPC端口>/<远端硬件参数>,transport=<底层类型>
url = "rpc:192.168.1.50:8000/COM3,transport=serial,baud=2000000"

with cio.connect(url) as dev:
    dev.write(b"Hello Remote Hardware\n")
```

---

## 八、多通道时序数据收集器 (`cio.Collector`)

`cio.Collector`（类名 `DataCollector`）是专为芯片产测、电压/电流/温度巡检、示波器波形捕获设计的极简时序数据收集器。

### 核心物理模型与设计准则：
1. **纯标准库 1D 时序向量（1D Vector Model）**：每个 Tag 是一条随时间独立生长的 1D 时序向量（允许通道间采样率不同、数据点长度不等），不存在强制对齐的 2D 矩阵假定。零第三方依赖，对 NumPy 天然友好。
2. **单一权威打点入口（Single Authority `collect`）**：淘汰割裂的多打点方法，所有打点统一收敛至 `collect(...)`（支持仿函数 `col(...)` 直接调用）。
3. **向量序列自动平铺展开**：传入 `list` / `tuple` 序列时默认按向量连续追加，无需 `batch=True` 等冗余开关。
4. **抗毛刺中位数优先（Median-First Statistics）**：针对硬件测量场景中的瞬态噪声毛刺（Glitch），内置抗干扰极强的 `col.median(tag)` 中位数计算。
5. **Crash-Safe 实时流式追加落盘**：初始化指定 `filepath` 时立即开启实时写缓冲；面对 `Ctrl+C` 中断或断电最大限度避免丢失数据，上下文退出时自动 Flush。

### 1. 构造函数
```python
col = cio.Collector(filepath: str | Path | None = None, *, buffer_size: int = 1000)
```
- `filepath`：可选实时流式追加落盘的 CSV 文件路径。
- `buffer_size`：写缓冲区打点阈值（默认 1000 点），达到后自动分批刷新至磁盘，退出上下文或销毁时全量刷盘。

### 2. 唯一打点方法 (`collect` / `__call__`)
```python
col.collect(*args, tag: str = "default", unit: str | None = None, timestamp: float | None = None, **kwargs)
```
- **多通道同时打点（最推荐）**：
  ```python
  col.collect(CH1=5.01, CH2=3.32, TEMP=25.4)
  # 支持携带共享时间戳
  col.collect(VBUS=5.0, IBUS=1.2, timestamp=time.time())
  ```
- **单值打点与携带单位**：
  ```python
  col.collect(5.05, tag="CH1", unit="V")
  # 仿函数快捷调用等价于 collect
  col(25.6, tag="TEMP", unit="°C")
  ```
- **一维波形序列自动展开**：
  ```python
  wave = [1.02, 1.05, 1.03, 1.08]
  col.collect(wave, tag="WAVEFORM", unit="V")
  ```

### 3. 数据检索与切片索引
- `col[tag] -> list[float | int]`：获取指定 Tag 的完整 1D 数值向量。
- `col[tag][idx] -> float | int`：读取单个点数值。
- `col[tag, slice] -> list[float | int]`：二维切片语法糖，直接获取指定区间数据（如 `col["CH1", :100]` 或 `col["CH1", -10:]`）。
- `col.timestamps(tag) -> list[float]`：获取指定 Tag 对应的时间戳向量。
- `col.tags() -> list[str]`：获取当前已记录的所有通道名称列表。
- `len(col)`：获取当前收集的总数据点数。

### 4. 统计与分析指标
```python
# 抗毛刺中位数（测量首选，消除瞬态脉冲毛刺）
mid = col.median("CH1")

# 均值与方差
avg = col.mean("CH1")
std = col.std("CH1")

# 极值
min_v = col.min("CH1")
max_v = col.max("CH1")

# 全量统计字典
stats = col.stats("CH1")
# {'count': 100, 'mean': 5.01, 'median': 5.01, 'std': 0.02, 'min': 4.98, 'max': 5.05, 'unit': 'V'}
```

### 5. 数据导出与呈现
- `col.to_csv(filepath: str | Path | None = None, *, tag: str | None = None) -> Path`：导出为标准时序 CSV；支持指定 `tag` 过滤单通道。
- `col.to_dict(copy: bool = True) -> dict[str, list[DataPoint]]`：获取通道到底层数据点对象的字典。
- `col.print_summary(title="DATA COLLECTION SUMMARY")`：在控制台打印美观的 ASCII 多通道统计数据看板。
- `col.clear(tag: str | None = None)`：清空全部通道或指定通道的内存数据。

### 6. 上下文管理器与生命周期
```python
with cio.Collector("experiment.csv") as col:
    for i in range(100):
        col.collect(CH1=i * 0.1, CH2=i * 0.2)
# 退出上下文自动 flush 文件句柄并安全关闭
```

---

## 九、数据类型与异常体系

### 1. 数据类型归一化 (`BytesLike`)
所有写入入参均声明为 `BytesLike = bytes | bytearray | int | list[int] | tuple[int, ...]`，内部通过 `cio.ensure_bytes()` 统一归一化：
- `dev.write(b"\x01\x02")`
- `dev.write([0x01, 0x02, 0x03])`
- `dev.write((0x01, 0x02))`
- `dev.write(0xFF)` （自动识别为 `b"\xFF"`）

### 2. 异常继承树 (`cio.exceptions`)
```text
TransportError (基类)
 ├── DriverMissingError (驱动或物理依赖缺失)
 │    ├── PythonPackageMissingError (缺少 pyserial / pyftdi 等 pip 包)
 │    └── CDllMissingError (缺少 visa32.dll 等 C 动态链接库)
 ├── UnsupportedCapabilityError (调用不支持的总线能力，同时派生自 AttributeError)
 ├── ConnectionError (连接建立失败)
 │    ├── ConnectTimeoutError (连接超时)
 │    └── ConnectionRefusedError (连接被拒绝)
 ├── IOOperationError (读写 I/O 操作失败)
 │    ├── ReadTimeoutError (读取超时 / read_until 未匹配)
 │    ├── WriteTimeoutError (写入超时)
 │    ├── BufferOverflowError (缓冲区溢出)
 │    ├── WriteError (写入失败)
 │    └── FrameChecksumError (帧校验 CRC/CheckSum 错误)
 ├── InvalidLocatorError (硬件定位器格式错误，InvalidUrlError 为其兼容别名)
```


---

## 十、即拷即用标准代码模板 (Recipes)

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

with cio.connect("spi[cb]:0,cs=0,trace=on @ serial:COM3,baud=2000000") as dev:
    # 发送 JEDEC ID 读取指令 0x9F，接收 3 字节厂商与设备 ID
    rx = dev.transfer([0x9F, 0x00, 0x00, 0x00])
    print(f"Manufacturer ID: 0x{rx[1]:02X}, Device ID: 0x{rx[2]:02X}{rx[3]:02X}")
```

### 模板 3：SCPI 可编程仪器与示波器交互 (VISA / TCP)
```python
import cio

# 方式 A: 原生 VISA 示波器交互（支持 USB-TMC、GPIB、TCPIP 仪器）
# 自动通过系统安装的 NI-VISA / Keysight VISA 驱动与 PyVISA 访问
with cio.visa("USB0::0x2A8D::0x9007::MY63160152::INSTR", timeout=5.0) as scope:
    # 1. 询问仪器标识（直接传 SCPI 字符串，严格按照 7-bit ASCII 编码交互并返回 str）
    idn = scope.query("*IDN?")
    print("Oscilloscope IDN:", idn)

    # 2. 发送控制指令（直接传 SCPI 字符串，自动补换行）
    scope.write("*CLS")
    scope.write(":AUToscale")

    # 3. 读取原始二进制波形数据（使用 query_raw 保证二进制零编码污染）
    raw_waveform = scope.query_raw(":WAV:DATA?")
    print("Raw Waveform bytes:", len(raw_waveform))

# 方式 B: 原生网络 TCP SCPI 仪器交互
with cio.connect("tcp:192.168.1.100:5025,trace=on") as dev:
    resp = dev.query(b"*IDN?\n")
    print("Instrument IDN:", resp)
```

### 模板 4：沁恒 CH347 高速 I2C 传感器采集与双串口并发通信
```python
import asyncio
import cio

async def main():
    # 1. 打开 CH347 硬件 I2C
    i2c = cio.connect("i2c:0,frequency=400000 @ ch347:0")
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
    async with cio.connect("serial:COM12,baud=115200") as u1, \
               cio.connect("serial:COM13,baud=115200") as u2:
        await u1.write(b"HELLO_CH347_UART")
        echo = await u2.read_exact(16)
        print("UART Loopback Echo:", echo)

    await i2c.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### 模板 5：示波器波形与多通道数据采集实时落盘 (`cio.Collector`)
```python
import time
import cio

# 实时流式追加至 CSV，抗异常中断
with cio.Collector("scope_measurements.csv") as col:
    # 模拟从示波器读取通道 1 波形点并从万用表读取供电
    for cycle in range(5):
        # 1. 多通道标量同时打点
        col.collect(VCC=3.30 + cycle * 0.01, ICC=0.15 + cycle * 0.005, TEMP=25.0 + cycle * 0.2)

        # 2. 模拟示波器读取到的波形向量段（自动平铺展开为时序向量）
        wave_chunk = [0.01 * i + cycle * 0.05 for i in range(10)]
        col.collect(wave_chunk, tag="CH1_WAVE", unit="V")

        time.sleep(0.01)

    # 3. 统计与中位数分析 (抗毛刺)
    print("VCC 均值:", col.mean("VCC"))
    print("VCC 中位数 (抗噪声):", col.median("VCC"))
    print("CH1 采样点总数:", len(col["CH1_WAVE"]))
    print("CH1 最新 5 点:", col["CH1_WAVE", -5:])

    # 4. 打印 ASCII 汇总看板
    col.print_summary("TEST RIG RUN 01")
```

