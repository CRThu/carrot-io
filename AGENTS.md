# AGENTS.md - 系统架构与 AI Agent 开发者手册

本文档为 `carrot-io`（包名：`cio`）硬件抽象层的**权威架构规范与 AI Agent 开发者手册**。旨在让 Agent 无需逐行通读源码即可获得全库精准心智模型。

> 💡 **相关文档**：
> - 📘 **用户态 API 手册**：[API.md](API.md)（URL 格式、总线方法签名、Verifier 测试模板）。
> - 📄 **下位机 ASCII 协议**：[CARROT_PROTOCOL.md](CARROT_PROTOCOL.md)。

---

## 1. 五层解耦架构与类继承体系

```text
 1. 顶层入口:    cio.connect() / cio.scan() / cio.tcp() / cio.serial() / cio.Verifier
 2. 协议桥层:    AsyncI2cBridge / AsyncSpiBridge / AsyncGpioBridge / RpcRemoteTransport
 3. 核心传输层:  AsyncBaseTransport -> AsyncStreamTransport / AsyncPacketTransport / AsyncI2cTransport / AsyncSpiTransport
 4. 后端适配器:  TcpTransport / UdpTransport / SerialTransport / Ftdi* / Visa* / Usb*
 5. 底层硬件驱动: asyncio Socket / PySerial / PyFTDI / C DLLs (visa32, libusb)
```

### 类继承拓扑
- **`AsyncBaseTransport`**（抽象基类：并发锁、`sync` 统一同步适配、`trace` 日志、`query`、析构）
  - **`AsyncStreamTransport`** (关联 `FifoBuffer`) $\rightarrow$ `AsyncUartTransport` (`SerialTransport`, `FtdiUartTransport`), `TcpTransport`, `RpcRemoteTransport`, `MockTransport`
  - **`AsyncPacketTransport`** (关联 `PacketQueue`) $\rightarrow$ `UdpTransport`, `UsbTransport`
  - **`AsyncI2cTransport`** $\rightarrow$ `AsyncI2cBridge`, `FtdiI2cTransport`
  - **`AsyncSpiTransport`** $\rightarrow$ `AsyncSpiBridge`, `FtdiSpiTransport`
- **`AsyncGpioPin`**（抽象 GPIO 引脚接口）$\rightarrow$ `AsyncGpioBridge`, `FtdiGpioPin`, `MockGpioPin`

---

## 2. 模块字典速查 (Module Map)

- **`cio.core`**（核心抽象层，**零第三方顶层依赖**）：
  - **`converters`**：集中类型别名 `BytesLike`、上行序列化 (`ensure_bytes`, `to_hex_str`, `format_arg`) 与下行反序列化 (`parse_int`, `parse_bool`, `parse_hex_bytes`, `parse_int_list`)。
  - **`base`**：`AsyncBaseTransport` 根类与通用 `SyncTransportWrapper` 同步调度器。
  - **`stream` / `packet` / `i2c` / `spi` / `gpio` / `uart`**：各硬件总线标准契约。
  - **`codec` / `protocol`**：数据编解码器与强类型协议绑定 (`dev.bind(codec)`)。
  - **`buffer`**：`FifoBuffer`（流式无界缓冲）与 `PacketQueue`（报文队列，支持 `DROP_OLDEST` / `BACKPRESSURE`）。
  - **`logger`**：`IoLogger`（热路径零开销内存线性队列，按需渲染 Hex/ASCII）。
  - **`factory` / `registry`**：URL Scheme 解析分发与静默探测设备扫描。
  - **`exceptions`**：分级异常体系（`DriverMissingError`, `ReadTimeoutError`, `IOOperationError` 等）。
- **`cio.composite`**（协议桥层）：`carrotbridge`（极简 ASCII 管道）、`i2c` / `spi` / `gpio`（硬件协议桥）、`rpc`（跨机代理）。
- **`cio.backends`**（延迟加载适配器）：`socket`, `serial`, `ftdi`, `visa`, `usb`。
- **`cio.testing`**（测试组件）：`mock`（内存 Mock 设备）、`verifier`（断言验证器）。

---

## 3. 核心架构约束与编码红线（Golden Rules）

1. **纯异步核心与统一通用同步适配（Pure Async Core & Universal Sync Wrapper）**：
   - 内部 100% 纯协程实现 (`async def`)，**严禁手写专属同步类**。
   - 外部同步统一通过 `dev.sync`（由 `SyncTransportWrapper` 驱动后台专用 Loop 线程调度）；`with dev:` 自动进入同步视图，`async with dev:` 保持原生异步。
2. **纯净顶层命名空间与零内部符号泄露（Clean Public API & Zero Symbol Pollution）**：
   - `cio/__init__.py` 与 `__all__` **仅暴露顶层核心公共入口**（工厂函数、总线基类、分级异常、`Verifier`、`BytesLike`、`ensure_bytes`）。
   - **严禁将内部转换工具（如 `format_arg`, `parse_*`, `to_hex_str`）泄露到顶层命名空间**。
   - **严禁在类中挂载冗余的 `staticmethod` 别名**，各模块直接从 `cio.core.converters` 显式导入所需函数。
3. **瘦基类接口与零抽象泄露（Lean ABC & Zero Abstraction Leakage）**：
   - 抽象基类（`AsyncI2cTransport` 等）只定义该总线不可替代的核心物理契约（`read`, `write`, `transfer`）。
   - 特定协议桥能力（如 `CarrotBridge` 的 `IIC.SCAN`, `SPEED`, `MODE`）**仅在对应 Composite 协议桥中实现**，严禁将其提升到基类作为 `@abc.abstractmethod` 污染其他物理后端。
   - 基类中的可选扩展方法声明，默认必须直接抛出 `raise NotImplementedError("...")`。
4. **严禁危险的纯软件伪兜底（No Dangerous Software Fallbacks / Zero Side Effects）**：
   - 严禁在缺少硬件支持时，用盲目的业务读写（如用 `read(addr, 1)` 轮询 112 个地址模拟 I2C scan）充当默认兜底。这会破坏从机状态机（导致 FIFO 出队、标志清空、指针自增）且因超时累积造成数秒卡死。
   - 硬件操作必须忠实对齐物理语义，不支持的功能直接显式抛异常。
5. **集中式数据转换与类型安全（Single Source of Converters）**：
   - 所有数据类型转换、入参格式化与出参反序列化**统一且仅在 `cio.core.converters` 中维护**。入参统一支持 `BytesLike`（`bytes`, `bytearray`, `int`, `list[int]`）并经由 `ensure_bytes` 归一化。
   - 严禁到处手写 Ad-hoc 的散装 Hex 转换或多重 `try-except` 弱类型猜测。
6. **热路径零开销与锁保护**：
   - `write()` 与 `read()` 内部严禁拼接 Hex 字符串或调用控制台打印；`write` 必须受 `self._write_lock` 保护，`read` 必须受 `self._read_lock` 保护。
7. **默认无需保留向后兼容包袱（No Backward Compatibility by Default）**：
   - 重构收敛时，保持代码极致精炼，无需保留废弃别名和过渡胶水层。破坏性改动前显式向用户确认。
8. **核心库零第三方顶层导入与分级探测错误（Zero-Dependency Core & Graceful Probing）**：
   - `cio.core.*` 必须仅使用 Python 标准库。第三方扩展包只能在 `cio.backends.*` 中延迟加载。
   - **扫描探测**（`cio.scan()`）：静默吞掉 `ImportError` / `OSError`，不中断主流程；
   - **主动连接**（`cio.connect()` / `dev.open()`）：驱动缺失时必须抛出携带明确安装指引的 `DriverMissingError`（如 `PythonPackageMissingError`, `CDllMissingError`）。
9. **先对齐后动手，严禁盲目修改（Discuss Before Modifying / Zero Guesswork）**：
   - 在需求存在歧义、实现方式不确定、涉及多条技术路线选型或潜在重大影响时，**严禁盲目修改核心代码或凭空猜测实现**。
   - 必须先进行充分的技术调研，梳理方案利弊与影响面，主动向用户发起讨论并达成一致共识后，方可着手实施代码。
10. **适量且合理的中文注释（Meaningful Comments & Intent First）**：
    - 在核心协议帧结构、复杂状态机流转、位运算、边界防御及非直观的架构决策处，**必须补充清晰、精炼的中文注释**。
    - 注释重点阐明“为什么这么设计（Why）”与“物理/硬件约束”，杜绝简单的代码复述式废话注释，确保代码可维护、可追溯。
11. **文档实时同步与过时清理（Documentation as Truth）**：
    - 每次代码重构、接口调整或符号迁移后，**必须第一时间同步更新相关设计文档（如 [API.md](API.md)、[CARROT_PROTOCOL.md](CARROT_PROTOCOL.md) 等）中的过时内容**。
    - 严禁代码已改动而文档仍残留旧接口、废弃参数或失效说明。
12. **测试同步补齐与防回归验证（Full Test Coverage & Regression Prevention）**：
    - 任何新特性、重构分支或异常防御修改，**必须同步补齐并更新对应的单元测试与集成测试用例**。
    - 提交前必须执行 `uv run --extra dev pytest -v -m "not hardware"`，确保 100% 测试通过且无隐蔽回归。
13. **及时暴露疑惑，严禁掩盖问题与盲目试错（Ask Early & Transparent Communication）**：
    - 遇到未解疑惑、非预期异常、硬件协议冲突或环境阻塞时，**严禁盲目乱试乱改、编写临时 Hack 补丁粉饰太平或静默吞异常掩盖问题**。
    - 必须第一时间停下，清晰梳理当前现象、核心矛盾与排查结果，主动向用户提出疑问并对齐确认。
