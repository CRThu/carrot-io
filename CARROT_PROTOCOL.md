# CarrotBridge 下位机硬件控制 ASCII 协议规范 (CarrotProtocol V1.0)

本文档定义 `carrot-io` (`cio`) 上位机与 MCU 下位机/单片机通过 `CarrotBridge` 进行通信的**极简 ASCII 硬件控制协议规范**。

---

## 1. 协议设计原则与通信格式

1. **传输介质**：基于无界字节流/串口/Socket（所有指令与响应均以 `\n` 结尾）。
2. **上行指令**：上位机 -> 下位机，格式为标准 C 语言函数调用语法 `FUNC(ARG1, ARG2, ...)\n`。
3. **下行响应**：下位机 -> 上位机，格式为 `[RETURN]: <VALUE>\n`。
4. **日志与文本**：非 `[RETURN]:` 开头的其他下行文本（如 `[MSG]: ...` 或 `DEBUG: ...`），上位机将静默记入 `IoLogger` 日志队列，不干涉指令 Future 的唤醒。

---

## 2. 核心硬件控制指令全集

### 2.1 GPIO 引脚控制指令

| 指令语法 | 示例 | 含义说明 | 预期下行响应 |
| :--- | :--- | :--- | :--- |
| `IO.W(pin, val)` | `IO.W(A1, 1)` | 设置 GPIO 引脚电平 (1: 高, 0: 低) | `[RETURN]: 1` / `0` |
| `IO.R(pin)` | `IO.R(A1)` | 读取 GPIO 引脚电平 | `[RETURN]: 1` / `0` |
| `IO.MODE(pin, mode)` | `IO.MODE(A1, OUT,PP)` | 设置 GPIO 模式 (`IN`, `OUT`, `OUT,PP`, `OUT,OD`) | `[RETURN]: 0` |
| `IO.PULL(pin, pull)` | `IO.PULL(A1, UP)` | 设置 GPIO 上下拉 (`NONE`, `UP`, `DOWN`) | `[RETURN]: 0` |

---

### 2.2 I2C 主机总线指令

| 指令语法 | 示例 | 含义说明 | 预期下行响应 |
| :--- | :--- | :--- | :--- |
| `IIC.W(addr, hex_data, len)` | `IIC.W(0x50, 0x1234, 2)` | 向指定 I2C 7位从机地址写入数据字节 | `[RETURN]: <written_len>` (如 `[RETURN]: 2`) |
| `IIC.R(addr, len)` | `IIC.R(0x50, 2)` | 从指定 I2C 7位从机地址读取指定字节数 | `[RETURN]: <0x_hex_data>` (如 `[RETURN]: 0xAABB`) |
| `IIC.SPEED(speed_hz)` | `IIC.SPEED(400000)` | 配置 I2C 总线速率 (Hz) | `[RETURN]: 0` |

---

### 2.3 SPI 主机总线指令

| 指令语法 | 示例 | 含义说明 | 预期下行响应 |
| :--- | :--- | :--- | :--- |
| `SPI.W(cs, hex_data, len)` | `SPI.W(0, 0xABCD, 2)` | 发送 SPI 数据 (不要求全双工接收) | `[RETURN]: <written_len>` (如 `[RETURN]: 2`) |
| `SPI.R(cs, len)` | `SPI.R(0, 4)` | 接收 SPI 数据 | `[RETURN]: <0x_hex_data>` (如 `[RETURN]: 0x12345678`) |
| `SPI.T(cs, hex_data, len)` | `SPI.T(0, 0xABCD, 2)` | 全双工收发 SPI 数据 | `[RETURN]: <0x_hex_data>` (如 `[RETURN]: 0x5566`) |
| `SPI.MODE(cpol, cpha)` | `SPI.MODE(0, 1)` | 配置 SPI 模式 (`CPOL`: 0/1, `CPHA`: 0/1) | `[RETURN]: 0` |
| `SPI.SPEED(speed_hz)` | `SPI.SPEED(10000000)` | 配置 SPI 总线时钟速率 (Hz) | `[RETURN]: 0` |

---

## 3. 下行 Payload 解析与编解码规范

下位机与上位机 Payload 详细编解码规则请参考：
- **CarrotRPC 官方规范与仓库**: [https://github.com/CRThu/CarrotRPC/](https://github.com/CRThu/CarrotRPC/)
