# AGENTS.md

## Project Overview

`carrot-io`（包名：`cio`）是一个极简、零顶层外部依赖、优雅降级的 Python 3.12+ 硬件抽象层与总线通信库，提供纯异步核心与统一通用同步调度能力。

> 💡 **相关文档**：
> - 📘 **用户态 API 手册**：[API.md](API.md)（URL 格式、总线方法签名、断言验证测试模板）。
> - 📄 **下位机 ASCII 协议**：[CARROT_PROTOCOL.md](CARROT_PROTOCOL.md)。

## Project Structure & Navigation

```text
 1. 顶层入口:    cio.dev / cio.connect() / cio.scan() / cio.register_bridge() / cio.tcp() / cio.udp() / cio.serial() / cio.ftdi() / cio.ch347() / cio.check()
 2. 协议桥层:    CarrotBridge / AsyncI2cBridge / AsyncSpiBridge / AsyncGpioBridge / RpcRemoteTransport
 3. 核心传输层:  AsyncBaseTransport -> AsyncStreamTransport / AsyncPacketTransport / AsyncI2cTransport / AsyncSpiTransport
 4. 后端适配器:  TcpTransport / UdpTransport / SerialTransport / Ftdi* / Ch347* / VisaTransport
 5. 底层驱动层:  asyncio Socket / PySerial / PyFTDI / CH347 DLL / C DLLs (visa32)
```

- `cio/core/`: 核心基类（`base`）、总线契约（`stream`, `packet`, `i2c`, `spi`, `gpio`, `uart`）、环境变量单例代理（`env`）、集中类型转换（`converters`）、无界缓冲（`buffer`）、热路径内存日志（`logger`）、工厂与静默探测（`factory`, `registry`）、分级异常（`exceptions`）、协议绑定（`codec`, `protocol`）
- `cio/composite/`: 硬件协议桥（`carrotbridge`、`i2c` / `spi` / `gpio` 总线桥）、跨机代理（`rpc`）
- `cio/backends/`: 延迟加载硬件适配器（`socket`, `serial`, `ftdi`, `ch347`, `visa`）
- `cio/testing/`: 测试组件（`mock` 设备、`verify` 纯粹断言子系统：`check`, `require`, `verify`, `VerificationSession`）

## Build & Test Commands

```bash
# 依赖安装与同步
uv sync --all-extras

# 自动化测试（CRITICAL: 本地与 CI 必须排除真实硬件测试）
uv run pytest -m "not hardware" -v           # 常规单测与 Mock 测试全量运行
uv run pytest tests/test_stream.py -v       # 指定测试文件运行
uv run pytest -m "loopback" -v              # 回环短接线测试（需物理串口/网络回环）
uv run pytest -m "hardware" -v              # 真实物理硬件在环测试（需连接硬件）

# 版本管理自动化（遵循 tool.bumpversion）
uv run bump-my-version bump patch           # 小版本升级
```

## Engineering Rules & Domain Invariants（核心领域契约）

1. **纯异步核心 + 通用同步适配（Pure Async Core & Universal Sync）**：
   - 内部 100% 纯协程实现 (`async def`)，**严禁编写专属同步类**。
   - 外部同步统一通过 `dev.sync`（由 `SyncTransportWrapper` 驱动后台专用 Loop 调度）；`with dev:` 自动进入同步视图，`async with dev:` 保持原生异步。
   - `AsyncGpioPin` 为独立抽象基类，同样挂载 `.sync` 包装器。
2. **环境单例与声明式注入（`cio.dev` Singleton & Injection）**：
   - `from cio import dev` 提供惰性初始化的全局单例代理。自动读取当前工作区 `.env` 或环境变量 `CIO_DEVICE`（或具名设备 `CIO_DEVICE_<NAME>`）。
   - 默认同步调用（`dev.write(...)`, `dev.i2c(...)`, `dev["power"].write(...)`），支持 `close_all_devices()` 安全回收。
3. **零第三方顶层依赖与分级探测（Zero-Dependency Core & Graceful Probing）**：
   - `cio.core.*` 必须仅使用 Python 标准库；外部驱动（`pyserial`, `pyftdi`, `pyvisa`）统一在 `cio.backends.*` 中延迟加载。
   - **探测扫描**（`cio.scan()`）：静默容错 `ImportError` / `OSError`，不中断主流程；
   - **主动连接**（`cio.connect()` / `dev.open()`）：驱动缺失时抛出携带明确安装指引的 `DriverMissingError`（派生自 `PythonPackageMissingError` 或 `CDllMissingError`）。
4. **瘦基类契约与零抽象泄露（Lean ABC & Zero Abstraction Leakage）**：
   - 抽象基类仅定义物理不可替代的核心契约（`read`, `write`, `transfer`）。
   - 特定协议桥能力（如 `CarrotBridge` 的 `IIC.SCAN`, `SPEED`, `MODE`）**仅在对应 Composite 协议桥中暴露**，严禁提升到基类污染其他物理后端；基类可选扩展方法默认显式抛出 `NotImplementedError`。
5. **严禁危险的软件伪兜底（Zero Dangerous Software Fallbacks）**：
   - 严禁在缺少硬件支持时使用软件业务读写（如用 `read(addr, 1)` 轮询 112 个地址模拟 I2C scan）充当默认兜底。这会破坏从机硬件状态机且因超时累积造成长时间卡死。硬件不支持的功能直接显式抛异常。
6. **集中式数据转换（Single Source of Converters）**：
   - 所有数据类型转换、入参格式化与出参反序列化**统一且仅在 `cio.core.converters` 中维护**。入参统一支持 `BytesLike`（`bytes | bytearray | int | list[int] | tuple[int, ...]`）并经由 `ensure_bytes` 归一化。严禁在类中挂载冗余静态别名或散装 Hex 转换。
7. **热路径零开销与锁的物理本质（Hardware Concurrency & Lock Discipline）**：
   - `write()` 与 `read()` 内部严禁拼接 Hex 字符串或调用控制台打印。
   - 底层流传输层（全双工通道）仅维护物理级的 `_write_lock` 和 `_read_lock` 防止缓冲区交错碎裂。
   - 请求-响应级的原子事务（Request-Response Transaction）归属于协议网关层（如 `CarrotBridge._transaction_lock`），严禁将事务锁下沉污染底层全双工流。
8. **硬件多路复用与所有权借用契约（Ownership & Borrowing Protocol）**：
   - **1 对 N 架构**：单一物理链路（如 `serial://COM3`）对应唯一底座实例（`SerialTransport` / `CarrotBridge`）。上层总线（I2C/SPI/GPIO）通过 `bridge.i2c()`、`bridge.spi()`、`bridge.gpio()` 借用信道衍生。
   - **所有权生命周期**：借用者调用 `close()` 或退出上下文时，**仅注销自身逻辑状态（`borrowed=True`），严禁级联关闭底层物理底座**；物理底座的显式 `close()` 或外层上下文退出才释放物理句柄。
   - **汇聚点排他**：多协议信道共用物理底层时，所有 ASCII 指令统一在 `CarrotBridge._transaction_lock` 处排队，从汇聚源头杜绝指令交错撞车与回包错位。
