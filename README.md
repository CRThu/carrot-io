# carrot-io (cio) - 极简硬件抽象层与总线通信库

> 极简、零顶层强依赖、优雅静默降级的高性能 Python 3.12+ 硬件抽象层与设备验证库。

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![PyPI Version](https://img.shields.io/pypi/v/carrot-io.svg)](https://pypi.org/project/carrot-io/)
[![Dependencies](https://img.shields.io/badge/dependencies-0%20hard-brightgreen.svg)](#安装)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`carrot-io`（导入包名：`cio`）为串口（UART）、工业仪器（VISA / 示波器 / SCPI）、总线外设（I2C / SPI / GPIO）、网络管道（TCP / UDP）及 CH347 多协议硬件底座提供了**统一的标准 RFC 3986 URL 访问模型**与**纯异步核心 + 统一同步调度**双模架构。

> 📖 **权威文档导航**：
> - 📘 **[用户态 API 参考与速查手册 (API.md)](API.md)**：包含全部 URL 语法、总线方法签名、断言验证测试模板。
> - 📄 **[下位机 ASCII 协议规范 (CARROT_PROTOCOL.md)](CARROT_PROTOCOL.md)**：MCU 下位机固件与协议桥交互格式。
> - 🛠️ **[架构规范与 AI Agent 开发者手册 (AGENTS.md)](AGENTS.md)**：分层解耦、并发锁与底层红线设计原则。

---

## 目录

- [一、安装与可选依赖](#一安装与可选依赖)
- [二、5 秒极速上手](#二5-秒极速上手)
- [三、典型硬件场景 (由浅入深)](#三典型硬件场景-由浅入深)
  - [1. 串口与以太网通信 (Serial / TCP)](#1-串口与以太网通信-serial--tcp)
  - [2. 示波器与工业仪器控制 (VISA / SCPI)](#2-示波器与工业仪器控制-visa--scpi)
  - [3. I2C 传感器与 SPI 外设读写](#3-i2c-传感器与-spi-外设读写)
  - [4. GPIO 引脚电平控制](#4-gpio-引脚电平控制)
  - [5. 沁恒 CH347 高速 USB 多协议底座](#5-沁恒-ch347-高速-usb-多协议底座)
- [四、生产力工程特性](#四生产力工程特性)
  - [1. 实时通信抓包高亮与故障历史 (`trace` / `dump_history`)](#1-实时通信抓包高亮与故障历史-trace--dump_history)
  - [2. 环境变量单例注入 (`from cio import dev`)](#2-环境变量单例注入-from-cio-import-dev)
  - [3. 芯片与硬件 DSL 验证断言 (`check` / `verify`)](#3-芯片与硬件-dsl-验证断言-check--verify)
  - [4. 跨网络透明 RPC 代理 (`rpc://`)](#4-跨网络透明-rpc-代理-rpc)
- [五、核心类与 API 极速速查 (Cheat Sheet)](#五核心类与-api-极速速查-cheat-sheet)
  - [1. 物理流传输类 (`AsyncStreamTransport` / `VisaTransport`)](#1-物理流传输类-asyncstreamtransport--visatransport)
  - [2. I2C 主机总线类 (`AsyncI2cTransport` / `AsyncI2cBridge`)](#2-i2c-主机总线类-asynci2ctransport--asynci2cbridge)
  - [3. SPI 主机总线类 (`AsyncSpiTransport` / `AsyncSpiBridge`)](#3-spi-主机总线类-asyncspitransport--asyncspibridge)
  - [4. GPIO 引脚控制类 (`AsyncGpioPin` / `AsyncGpioBridge`)](#4-gpio-引脚控制类-asyncgpiopin--asyncgpiobridge)
  - [5. 协议编解码器 (`dev.bind(codec)`)](#5-协议编解码器-devbindcodec)
  - [6. 测试验证断言与记分板 (`cio.testing.verify`)](#6-测试验证断言与记分板-ciotestingverify)
  - [7. 顶层入口与快捷构造 (`cio.*`)](#7-顶层入口与快捷构造-cio)
- [六、自动化测试](#六自动化测试)
- [七、开源协议](#七开源协议)

---

## 一、安装与可选依赖

核心库保持**零第三方强依赖**，仅使用 Python 3.12+ 标准库。外部驱动按需延迟加载：

```bash
# 使用 uv (推荐)
uv add carrot-io                  # 核心库 (支持 TCP/UDP/RPC/Mock，零额外依赖)
uv add "carrot-io[serial]"        # 串口支持 (pyserial)
uv add "carrot-io[visa]"          # 示波器与工业仪表支持 (pyvisa)
uv add "carrot-io[ftdi]"          # FTDI 芯片支持 (pyftdi)
uv add "carrot-io[all]"           # 全量依赖安装

# 使用 pip
pip install "carrot-io[serial,visa]"
```

---

## 二、5 秒极速上手

无论是自动化脚本还是交互式终端，`cio` 支持统一的 URL 连接与**无缝同步/异步自动切换**：

```python
import cio

# 1. 一键静默扫描系统在线设备（自动跳过未安装驱动的后端）
print(cio.scan())

# 2. 同步模式：直接使用 with 上下文（常规测试脚本最爱，零异步心智负担）
with cio.connect("serial://COM3?baud=115200") as dev:
    dev.write(b"PING\n")
    print(dev.read_until(b"\n"))

# 3. 异步模式：使用 async with 保持原生高性能协程调度
# async with cio.connect("serial://COM3?baud=115200") as dev:
#     await dev.write(b"PING\n")
#     print(await dev.read_until(b"\n"))
```

---

## 三、典型硬件场景 (由浅入深)

### 1. 串口与以太网通信 (Serial / TCP)

支持精确字节读取、定界符截取与超时控制：

```python
import cio

# 串口设备
with cio.serial("COM3", baud=115200, timeout=2.0) as dev:
    dev.write(b"AT+GMR\r\n")
    response = dev.read_until(b"OK\r\n")
    print("AT Response:", response)

# 以太网 TCP 设备 (例如网口仪表或嵌入式设备端口)
with cio.tcp("192.168.1.100", 5025, timeout=3.0) as dev:
    dev.write(b"*IDN?\n")
    print("TCP Reply:", dev.read_until(b"\n"))
```

### 2. 示波器与工业仪器控制 (VISA / SCPI)

支持 USB-TMC、GPIB、TCPIP 等符合 VISA 规范的仪器设备。兼容系统已安装的 **NI-VISA**、**Keysight VISA** 驱动与纯 Python 后端：

```python
import cio

# 扫描连接的所有 VISA 仪器 (自动列出示波器、万用表等)
instruments = cio.scan("visa")
print("Found Instruments:", instruments)

# 原生字符串重载：直接传入 SCPI 字符串，自动补齐换行并解码返回 str
with cio.visa("USB0::0x2A8D::0x9007::MY63160152::INSTR", timeout=5.0) as scope:
    # 问答式查询
    idn = scope.query("*IDN?")
    print("示波器型号与版本:", idn)

    # 发送配置控制指令
    scope.write("*CLS")
    scope.write(":AUToscale")

    # 若需要读取波形数据块等原始二进制，直接传入 bytes 即可获取原始 bytes
    # raw_wave = scope.query(b":WAV:DATA?\n")
```

### 3. I2C 传感器与 SPI 外设读写

通过标准 URL 语法直连单片机/测试桥底座（默认串口通讯，下位机运行 CarrotBridge 固件）：

```python
import cio

# I2C 总线操作 (自动推导为串口底层通信)
with cio.connect("i2c://COM3?baud=2000000&reg_len=2") as i2c:
    # 扫描在线从机地址
    slaves = i2c.scan()
    print("Online I2C Slaves:", [hex(s) for s in slaves])

    # 读写 16 位寄存器 (支持直接传入 int、列表或 bytes)
    i2c.write_reg(addr=0x57, reg=0x0100, data=[0xAA, 0x55])
    val = i2c.read_reg(addr=0x57, reg=0x0100, nbytes=2)
    print("Reg 0x0100:", val.hex())

# SPI 总线全双工收发 (例如读取 SPI Flash JEDEC ID)
with cio.connect("spi://COM3?baud=2000000&cs=0") as spi:
    # 发送 0x9F 命令，同时读回 3 字节厂商与设备 ID
    rx = spi.transfer([0x9F, 0x00, 0x00, 0x00])
    print(f"SPI Flash ID: 0x{rx[1]:02X}{rx[2]:02X}{rx[3]:02X}")
```

### 4. GPIO 引脚电平控制

```python
import cio

with cio.connect("gpio://COM3?pin=1") as gpio:
    gpio.set_high()
    print("Current Level:", gpio.read_level())
    gpio.toggle()
```

### 5. 沁恒 CH347 高速 USB 多协议底座

支持利用单一 CH347 芯片同时进行原生硬件 I2C/SPI 操作与双串口全双工收发：

```python
import cio

# 打开 CH347 硬件原生 I2C 主机 (400kHz)
with cio.connect("i2c://0?transport=ch347&frequency=400000") as i2c:
    i2c.write(0x44, [0x24, 0x00])
    data = i2c.read(0x44, 6)
    print("Sensor Data:", data.hex())
```

---

## 四、生产力工程特性

### 1. 实时通信抓包高亮与故障历史 (`trace` / `dump_history`)

无需任何第三方抓包器，在任意 URL 尾部追加 `?trace=on` 即可在控制台实时微秒级高亮打印 TX/RX 报文：

```python
import cio

# 开启实时报文跟踪
with cio.connect("serial://COM3?baud=115200&trace=on") as dev:
    dev.write(b"HELLO")
    dev.read(5)

    # 任何时候可调取最近通讯历史（用于错误报告或记录日志）
    print(dev.dump_history(limit=10))
```

### 2. 环境变量单例注入 (`from cio import dev`)

通过 `.env` 或环境变量 `CIO_DEVICE` 声明设备，脚本内直接调用，彻底消除测试脚本中的硬编码端口：

```bash
# 在当前目录 .env 文件中声明
CIO_DEVICE="visa://USB0::0x2A8D::0x9007::MY63160152::INSTR"
```

```python
from cio import dev

# 无需手动 connect，开箱即用，进程退出时由 atexit 自动安全释放句柄
idn = dev.query("*IDN?")
print("Auto-injected device:", idn)
```

### 3. 芯片与硬件 DSL 验证断言 (`check` / `verify`)

专为芯片寄存器回归测试与产测冒烟脚本打造，提供掩码过滤、Hex 对齐比对与记分板看板：

```python
import cio
from cio import check, require, verify

with cio.connect("i2c://COM3") as i2c:
    verify.reset()

    # 1. check 记录断言结果并不中断执行；支持掩码比对
    check(i2c.read_reg(0x57, 0x00, 1), 0x07, mask=0x07, name="STATUS_REG")

    # 2. require 遇到错误立即中断并输出现场 Hex Diff
    require(i2c.read_reg(0x57, 0x01, 1), 0x10, name="CHIP_ID")

    # 3. 打印本次测试看板
    verify.summary()
```

### 4. 跨网络透明 RPC 代理 (`rpc://`)

远端主机启动服务，本地直接透明控制远端硬件，协议自动解包转发：

```bash
# 远端主机一行启动网关
python -c "import asyncio, cio; asyncio.run(cio.start_rpc_server('0.0.0.0', 8000))"
```

```python
# 本地透明代理调用
with cio.connect("rpc://192.168.1.50:8000/COM1?baud=115200") as dev:
    dev.write(b"HELLO")
```

### 5. 多通道数据采集与实时落盘 (`cio.Collector`)

测试中散落在各处的测量值，通过统一单一方法 `collect(...)` 汇聚，每个 Tag 天然作为独立 1D 向量存储：

```python
import cio

# 打开收集器 (指定文件则实时流式追加落盘，Crash-Safe 防断电数据丢失)
with cio.Collector("run.csv") as col:
    # 1. 关键字多通道同时打点 (最直观)
    col.collect(CH1=5.01, CH2=3.32, TEMP=25.4)
    # 2. 单点打点带单位
    col.collect(5.05, tag="CH1", unit="V")
    # 3. 连续波形向量直接注入
    col.collect([1.1, 1.2, 1.3], tag="WAVE")
    # 4. 直接获取 1D 向量与切片
    print(col["CH1"][:2])  # [5.01, 5.05]
    # 5. 抗毛刺中位数与均值
    print("中位数:", col.median("CH1"))
    # 6. 一键终端看板
    col.print_summary()
```

---

## 五、核心类与 API 极速速查 (Cheat Sheet)

无需每次翻阅底层源码与完整手册，核心类名、方法签名与极简用法速查：

### 1. 物理流传输类 (`AsyncStreamTransport` / `VisaTransport`)
> 适用于：串口、TCP、VISA 示波器与工业仪器、FTDI

| API 方法 | 概述与说明 | 极简调用示例 |
|---|---|---|
| `write(data)` | 发送数据（支持 `bytes` 原始字节流；VISA 下支持 `str` 自动补换行） | `dev.write(b"PING\n")` / `scope.write("*RST")` |
| `read(nbytes=-1)` | 从缓冲区读取指定字节数（`-1` 读取当前所有可用字节） | `data = dev.read()` |
| `read_until(delimiter)` | 读取直到遇到目标定界符（如换行符 `b"\n"`） | `line = dev.read_until(b"\n")` |
| `read_exact(n)` | 精确读取固定字节数（未读满前保持阻塞/等待直到超时） | `data = dev.read_exact(16)` |
| `query(cmd, delay=0)` | 原子事务：发送指令并立即读取回包（VISA 下传入 `str` 自动返回解码 `str`） | `idn = scope.query("*IDN?")` |
| `flush()` / `clear()` | 避脏缓冲区：清空底层 OS 物理驱动 FIFO 与内部缓冲（VISA 下触发 `viClear`） | `dev.flush()` / `scope.clear()` |
| `dump_history(limit)` | 导出最近 TX/RX 通讯日志字符串（微秒时间戳、方向、Hex 对齐） | `print(dev.dump_history(10))` |

### 2. I2C 主机总线类 (`AsyncI2cTransport` / `AsyncI2cBridge`)
> 适用于：I2C 传感器、EEPROM、外设配置芯片

| API 方法 | 概述与说明 | 极简调用示例 |
|---|---|---|
| `scan()` | 扫描 I2C 总线并返回所有在线从机的 7 位地址列表 | `slaves = i2c.scan()` |
| `read_reg(addr, reg, nbytes=1)` | 读取从机指定寄存器（自动应用全局或局部 `reg_len` 字节数） | `val = i2c.read_reg(0x57, 0x01, 1)` |
| `write_reg(addr, reg, data)` | 写入从机指定寄存器（数据支持直接传入 `int`、`list` 或 `bytes`） | `i2c.write_reg(0x57, 0x01, [0xAA, 0x55])` |
| `read(addr, nbytes)` | 从指定从机裸读原始字节流 | `raw = i2c.read(0x44, 6)` |
| `write(addr, data)` | 向指定从机裸发送数据序列 | `i2c.write(0x44, [0x24, 0x00])` |

### 3. SPI 主机总线类 (`AsyncSpiTransport` / `AsyncSpiBridge`)
> 适用于：SPI Flash、高速 ADC/DAC、外置通信芯片

| API 方法 | 概述与说明 | 极简调用示例 |
|---|---|---|
| `transfer(tx_data)` | 全双工同步收发：发出 `tx_data` 的同时读回等长数据 | `rx = spi.transfer([0x9F, 0x00, 0x00, 0x00])` |

### 4. GPIO 引脚控制类 (`AsyncGpioPin` / `AsyncGpioBridge`)
> 适用于：硬件复位引脚、片选 CS 控制、电平检测与边沿中断

| API 方法 | 概述与说明 | 极简调用示例 |
|---|---|---|
| `set_high()` / `set_low()` | 将 GPIO 输出拉高至 3.3V 或拉低至 0V | `gpio.set_high()` / `gpio.set_low()` |
| `toggle()` | 翻转 GPIO 输出电平 | `gpio.toggle()` |
| `read_level()` | 读取 GPIO 输入电平（返回 `bool`: `True` 为高，`False` 为低） | `if gpio.read_level(): ...` |
| `wait_for_edge(edge, timeout)` | 阻塞/异步等待电平跳变（`"rising"` / `"falling"` / `"both"`） | `gpio.wait_for_edge("rising", timeout=1.0)` |

### 5. 协议编解码器 (`dev.bind(codec) -> ProtocolTransport`)
> 适用于：为底层生肉字节管道绑定强类型结构化帧收发

| Codec 类名 | 概述与应用场景 | 极简绑定示例 |
|---|---|---|
| `LineCodec(delimiter=b"\n")` | 文本定界符行协议，直接读写 `str`（SCPI / NMEA / AT 指令） | `proto = dev.bind(LineCodec())` |
| `FramedBinaryCodec(...)` | 工业二进制帧 `[HEADER][LEN][PAYLOAD][CRC]` 自动寻头与校验 | `proto = dev.bind(FramedBinaryCodec(header=b"\xAA\x55", crc_type="crc16"))` |
| `StructCodec(fmt)` | 基于 Python `struct` 格式串打包/解包原生元组（如 `">IH"`） | `proto = dev.bind(StructCodec(">IH"))` |

### 6. 测试验证断言与记分板 (`cio.testing.verify`)
> 适用于：芯片寄存器冒烟测试、产测判断看板

| 函数名 | 概述与说明 | 极简调用示例 |
|---|---|---|
| `check(actual, expected, name, mask)` | 软断言：比对数值/字节、支持位掩码过滤，失败记录看板但不中断脚本 | `check(reg, 0x07, mask=0x07, name="STATUS")` |
| `require(actual, expected, name)` | 强断言：比对失败立即抛出异常中断执行，并输出现场对齐 Hex Diff | `require(chip_id, 0x10, name="CHIP_ID")` |
| `verify.summary()` | 打印当前会话测试统计记分板；若无失败返回 `True` | `passed = verify.summary()` |

### 7. 顶层入口与快捷构造 (`cio.*`)
| 函数 / 对象 | 概述与说明 | 极简调用示例 |
|---|---|---|
| `cio.connect(url)` | 万能 URL 工厂，自动解析 Scheme 并挂载对应物理驱动或协议桥 | `cio.connect("i2c://COM3?baud=2000000")` |
| `cio.scan(kind=None)` | 静默探测并返回系统在线设备列表（可指定 `"visa"`, `"serial"` 等） | `cio.scan("visa")` / `cio.scan()` |
| `cio.serial()`, `cio.tcp()`, `cio.visa()`, `cio.ch347()` | 显式快捷工厂函数，快速建立特定物理信道 | `cio.visa("USB0::...")` / `cio.serial("COM3")` |
| `from cio import dev` | 声明式环境变量单例代理，按工作区 `.env` 自动按需连接 | `dev.write(...)` |
| `cio.Collector("run.csv")` | 多通道时序数据收集器，支持实时流式落盘与中位数抗干扰统计 | `with cio.Collector() as col: ...` |

### 8. 多通道时序数据收集器 (`cio.Collector`)
> 适用于：电压/电流/温度巡检、示波器波形捕获、抗毛刺中位数统计与实时 CSV 写入

| API 方法 | 概述与说明 | 极简调用示例 |
|---|---|---|
| `collect(*args, tag="default", unit=None, **kwargs)` | 单一权威打点入口（支持单点、多通道关键字、向量序列自动展开） | `col.collect(CH1=5.01, CH2=3.3)` / `col.collect([1.1, 1.2], tag="W")` |
| `col[tag]` / `col[tag, slice]` | 1D 数值向量检索与快捷切片提取 | `col["CH1"][:100]` / `col["CH1", -10:]` |
| `median(tag)` | 抗毛刺中位数统计（消除瞬态噪声毛刺的首选） | `mid = col.median("CH1")` |
| `mean(tag)` / `min(tag)` / `max(tag)` / `std(tag)` | 基础均值、极值与标准差统计 | `avg = col.mean("CH1")` |
| `to_csv(filepath, *, tag=None)` | 导出为标准时序 CSV 文件（支持单 Tag 过滤） | `col.to_csv("dump.csv")` |
| `print_summary()` | 在终端打印格式化 ASCII 多通道统计数据看板 | `col.print_summary()` |

---

## 六、自动化测试

`cio` 拥有完备的自动化测试矩阵。常规单元测试与真实硬件在环测试实现了严格的物理隔离：

```bash
# 运行常规单元测试与边界测试 (CI 默认模式，秒级全量执行，零硬件依赖)
uv run pytest -m "not hardware" -v

# 运行真实物理示波器/硬件在环测试 (需连接实际硬件)
uv run pytest tests/test_visa_hardware.py -m hardware -v
```

---

## 七、开源协议

本项目采用 [MIT License](LICENSE) 许可开源。
