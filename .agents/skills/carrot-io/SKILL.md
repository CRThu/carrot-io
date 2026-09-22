---
name: carrot-io
description: >-
  Hardware communication, bus abstraction (I2C/SPI/GPIO/UART), NFC reader/card testing,
  and chip automated verification with carrot-io (cio). Use when interacting with physical
  or mock hardware, writing register test scripts, connecting to devices via URL, or asserting hardware responses.
---

# Carrot-IO (cio) Hardware Interaction & Verification Skill

`carrot-io` (`cio`) 是专为硬件总线通信、芯片自动化测试与验证设计的轻量级统一硬件抽象层（Python 3.12+）。内部 100% 异步核心，对外提供无感知的同步/异步双模调度与全局单例注入。

---

## 1. 标准 URL 体系 (RFC 3986 Standard URIs)

统一遵循标准单 Scheme 格式：`{contract}://{address}?{params}`。总线协议桥默认基于串口物理底座，异构硬件或网络端点显式通过 `?transport=` 指定。

| 目标总线 / 领域 | 标准 URL 示例 | 底座与参数说明 |
| :--- | :--- | :--- |
| **I2C 总线** | `i2c://COM3?baud=2000000&reg_len=2` | 默认串口底座并挂接 CarrotBridge；`reg_len` 指定默认寄存器地址字节长 |
| **I2C (专用芯片)** | `i2c://0?transport=ch347&frequency=400000` | 显式指定沁恒 CH347 高速硬件 I2C 后端 |
| **SPI 总线** | `spi://COM3?baud=2000000&cs=0` | 默认串口底座；`cs` 指定片选引脚编号 |
| **SPI (网络桥)** | `spi://192.168.1.100:5025?transport=tcp&clock=10MHz` | 显式指定 TCP 底座并挂接 SPI 协议桥 |
| **GPIO 引脚** | `gpio://COM3?pin=1` | 默认串口底座；返回 `AsyncGpioPin` 引脚句柄 |
| **原始串口流** | `serial://COM3?baud=115200` | 原生全双工串口通信管道 |
| **TCP / SCPI** | `tcp://192.168.1.100:5025` | 原生 TCP 网络字节流 |
| **NFC 读卡器** | `nfc://COM3?driver=pn532` | 统一 NFC 入口（支持 `pn532`, `clrc663`） |
| **远程 RPC 代理** | `rpc://192.168.1.50:8000/COM1?baud=115200` | 跨网络控制远程主机串口硬件 |
| **虚拟测试** | `mock://` 或 `i2c://mock` | 纯软件 Mock 内存设备，用于单元测试与 CI |

> **通用查询参数**：
> - `trace=on`：启用热路径内存日志追踪（不中断热路径，可通过 `dev.history` 调阅）。
> - `timeout=2.0`：统一 I/O 超时（秒）。
> - `bridge=cb`（默认）或自定义协议桥名称。

---

## 2. 极简芯片验证与 DSL 脚本范式

利用当前工作区目录 `.env` 与惰性单例 `dev`，无需样板代码即可直接编写测试：

### ① 配置文件 `.env`
```bash
CIO_DEVICE="i2c://COM3?baud=2000000&reg_len=2&trace=on"
CIO_DEVICE_POWER="serial://COM4?baud=9600"
```

### ② 验证脚本
```python
from cio import dev, check, require, verify

# 1. 重置断言看板
verify.reset()

# 2. 默认设备操作（同步阻塞视图，读取 CIO_DEVICE）
with dev:
    # 软断言：校验失败计入记分板，不中断后续测试
    check(dev.read_reg(0x57, 0xFFB1, 1), 0x07, name="STATUS_REG")
    
    # 寄存器写与读回校验
    dev.write_reg(0x57, 0xFFB4, 0x03)
    check(dev.read_reg(0x57, 0xFFB4, 1), 0x03, name="REG_FFB4_RW")

    # 位掩码过滤断言
    check.mask(dev.read_reg(0x57, 0xFFB0, 1), 0x10, mask=0x10, name="READY_BIT")

# 3. 具名辅设备调用（读取 CIO_DEVICE_POWER）
dev["power"].write("VSET 3.3\n")

# 4. 打印结构化测试看板
verify.summary()
```

---

## 3. 双模上下文与调度准则

- **同步测试（日常脚本与交互）**：
  ```python
  import cio
  with cio.connect("i2c://COM3?baud=2000000") as dev:
      data = dev.read_reg(0x57, 0xFFB0, 1)  # 直接调用，内部由专用 Loop 调度
  ```
- **异步高并发（服务与网关）**：
  ```python
  import asyncio
  import cio
  async def main():
      async with cio.connect("i2c://COM3?baud=2000000") as dev:
          data = await dev.read_reg(0x57, 0xFFB0, 1)
  asyncio.run(main())
  ```
- **属性动态切换**：任何对象均提供 `.sync` 属性切至同步。

---

## 4. 核心总线 API 契约

### ① I2C 总线 (`AsyncI2cTransport`)
- `dev.read(addr: int, nbytes: int) -> bytes`：从机纯读取。
- `dev.write(addr: int, data: BytesLike) -> int`：向从机纯写入。
- `dev.read_reg(addr: int, reg: int, nbytes: int, reg_len: int | None = None) -> bytes`：原子读寄存器。
- `dev.write_reg(addr: int, reg: int, data: BytesLike, reg_len: int | None = None) -> int`：写寄存器。
- `dev.scan() -> list[int]`：扫描物理在线设备地址列表。

### ② SPI 总线 (`AsyncSpiTransport`)
- `dev.transfer(data: BytesLike) -> bytes`：全双工同时收发数据。
- `dev.write(data: BytesLike) -> int`：仅发送。
- `dev.read(nbytes: int) -> bytes`：仅读取。

### ③ GPIO 引脚 (`AsyncGpioPin`)
- `pin.set_high()`, `pin.set_low()`, `pin.toggle()`：电平控制。
- `pin.read_level() -> bool`：读取输入电平。
- `pin.config_mode("OUT,PP")` / `pin.config_pull("UP")`：配置推挽/开漏与上下拉。
- `pin.wait_for_edge("rising", timeout=2.0) -> bool`：中断边沿等待。

### ④ 串口/数据流与编解码器 (`dev.bind()`)
```python
from cio import LineCodec
proto = dev.bind(LineCodec(delimiter=b"\n"))
proto.write("*IDN?")
idn = proto.read(timeout=2.0)
```

---

## 5. 硬件多路复用与所有权借用 (1 对 N 架构)

单一串口物理链路共用时，通过 Bridge 派生子信道，**借用者退出上下文不关闭底层物理串口**：

```python
with cio.serial("COM3", baud=2000000) as bridge:
    i2c = bridge.i2c(reg_len=2)
    pin = bridge.gpio(pin=1)
    
    pin.set_high()
    i2c.write_reg(0x57, 0x00, 0x01)
    pin.set_low()
```

---

## 6. 断言验证子系统速查 (`cio.testing.verify`)

- `check(actual, expected, name="...")`：软断言（数值、字节、列表或 Hex 字符串）。
- `check.mask(actual, expected, mask=0xFF, name="...")`：带掩码软断言。
- `check.within(actual, min_val, max_val, name="...")`：范围断言。
- `require(actual, expected, name="...")`：强断言（不通过立即抛出 `AssertionError` 熔断）。
- `verify.reset()`：重置会话。
- `verify.summary(title="...", show_all=True) -> bool`：打印全量记分板，全部 PASS 返回 `True`。

---

## 7. 多通道数据收集器速查 (`cio.Collector`)

专为示波器波形采样、供电/温度打点与抗毛刺分析设计：

```python
with cio.Collector("measurements.csv") as col:
    # 1. 唯一权威方法打点 (多通道关键字同时打点或单通道带单位)
    col.collect(VCC=3.3, ICC=0.12, TEMP=25.4)
    col.collect(5.01, tag="CH1", unit="V")
    
    # 2. 向量连续波形直接注入 (自动平铺展开)
    col.collect([1.1, 1.2, 1.3], tag="WAVE")

    # 3. 1D 向量检索与二维快捷切片
    recent_vcc = col["VCC", -10:]
    wave_slice = col["WAVE"][:100]

    # 4. 抗毛刺中位数与基础统计
    mid = col.median("VCC")
    avg = col.mean("VCC")

    # 5. 格式化控制台看板
    col.print_summary()
```

---

## 8. 异常处理与排错指南

- `DriverMissingError`：缺少底层驱动（如 `pyserial` 或 `CH347DLL`），附带安装指令。
- `InvalidUrlError`：URL 格式非法（特别包含旧式 `+` 语法）。
- `BusTimeoutError`：通信超时，检查接线、波特率或从机供电。
- `UnsupportedCapabilityError`：调用了当前硬件不支持的功能。
- **获取实时数据流排查**：
  ```python
  for record in dev.history:
      print(f"[{record.direction}] {record.payload.hex()}")
  ```

