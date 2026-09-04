"""
WCH CH347 High-Speed Multi-Protocol Bridge Backend (UART, I2C, SPI, GPIO).
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import sys
from importlib.resources import files
from typing import Any, Literal

from cio.core.base import AsyncBaseTransport
from cio.core.converters import BytesLike, ensure_bytes, parse_int
from cio.core.exceptions import CDllMissingError, ConnectionError, IOOperationError
from cio.core.gpio import AsyncGpioPin
from cio.core.i2c import AsyncI2cTransport
from cio.core.registry import registry
from cio.core.spi import AsyncSpiTransport

# --- C 结构体与类型定义 ---

class mSpiCfgS(ctypes.Structure):
    _fields_ = [
        ("iMode", ctypes.c_ubyte),                  # 0-3: SPI Mode 0/1/2/3
        ("iClock", ctypes.c_ubyte),                 # 0=60MHz, 1=30MHz, 2=15MHz, 3=7.5MHz, 4=3.75MHz, 5=1.875MHz, 6=937.5KHz, 7=468.75KHz
        ("iByteOrder", ctypes.c_ubyte),             # 0=LSB, 1=MSB
        ("iSpiWriteReadInterval", ctypes.c_ushort),  # 字节间隔(us)
        ("iSpiOutDefaultData", ctypes.c_ubyte),     # 读取时默认输出数据
        ("iChipSelect", ctypes.c_ulong),            # 片选控制: bit7=1使能片选, bit0=CS1, bit1=CS2
        ("CS1Polarity", ctypes.c_ubyte),            # CS1极性: 0=低有效, 1=高有效
        ("CS2Polarity", ctypes.c_ubyte),            # CS2极性: 0=低有效, 1=高有效
        ("iIsAutoDeativeCS", ctypes.c_ushort),       # 操作后是否自动撤除CS
        ("iActiveDelay", ctypes.c_ushort),           # CS有效后延时
        ("iDelayDeactive", ctypes.c_ulong),          # CS撤除延时
    ]

class mDeviceInforS(ctypes.Structure):
    _fields_ = [
        ("iIndex", ctypes.c_ubyte),
        ("DevicePath", ctypes.c_char * 260),
        ("UsbClass", ctypes.c_ubyte),
        ("DataDnEndp", ctypes.c_ubyte),
        ("ProductString", ctypes.c_char * 64),
        ("ManufacturerString", ctypes.c_char * 64),
        ("WriteTimeout", ctypes.c_ulong),
        ("ReadTimeout", ctypes.c_ulong),
        ("FuncDescStr", ctypes.c_char * 64),
        ("FirewareVer", ctypes.c_ubyte),
        ("_reserved", ctypes.c_ubyte * 512),  # 垫高缓冲区，防止不同版本 DLL 结构体溢出
    ]

# --- 动态链接库三级定位器 (无环境变量依赖，优先包内资源) ---

def _find_ch347_dll_path() -> str | None:
    # 1. 允许显式环境变量覆盖 (开发调试后门)
    env_path = os.environ.get("CIO_CH347_DLL")
    if env_path and os.path.isfile(env_path):
        return env_path

    is_64bit = sys.maxsize > 2**32
    dll_name = "CH347DLLA64.DLL" if is_64bit else "CH347DLL.DLL"
    arch_dir = "win_x64" if is_64bit else "win_x86"

    # 2. 官方推荐规范：通过 importlib.resources 定位包内内置 DLL
    try:
        builtin_dll = files("cio.backends").joinpath("libs", arch_dir, dll_name)
        if builtin_dll.is_file():
            return str(builtin_dll)
    except Exception:
        pass

    # 3. 沁恒官方驱动解压安装默认目录兜底
    wch_default = os.path.join(r"C:\WCH.CN\CH341PAR", dll_name)
    if os.path.isfile(wch_default):
        return wch_default

    return None

def _load_ch347_dll() -> ctypes.CDLL | None:
    path = _find_ch347_dll_path()
    if not path:
        return None
    try:
        if sys.platform == "win32":
            return ctypes.windll.LoadLibrary(path)
        return ctypes.cdll.LoadLibrary(path)
    except (OSError, Exception):
        return None

def _probe_ch347() -> bool:
    return _load_ch347_dll() is not None

def _scan_ch347() -> list[dict[str, Any]]:
    dll = _load_ch347_dll()
    if not dll:
        return []
    devices = []
    # 扫描索引 0-7
    for idx in range(8):
        try:
            handle = dll.CH347OpenDevice(idx)
            # INVALID_HANDLE_VALUE = -1 (即 64 位无符号 0xFFFFFFFFFFFFFFFF)
            if handle not in (-1, 0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF):
                info = mDeviceInforS()
                desc = "CH347 USB Multi-Function Device"
                if hasattr(dll, "CH347GetDeviceInfor") and dll.CH347GetDeviceInfor(idx, ctypes.byref(info)):
                    try:
                        desc = info.ProductString.decode("ascii", errors="ignore").strip() or desc
                    except Exception:
                        pass
                devices.append({
                    "scheme": "ch347",
                    "index": idx,
                    "description": desc,
                })
                dll.CH347CloseDevice(idx)
        except Exception:
            continue
    return devices

# --- 单物理底座管理器 (1 对 N 所有权借用架构) ---

class Ch347Device:
    """
    Physical hardware owner managing CH347 device handle, thread-safe transaction locks,
    and multi-bus derived channels borrowing.
    """
    _instances: dict[int, Ch347Device] = {}

    @classmethod
    def get_or_create(cls, dev_index: int = 0) -> Ch347Device:
        if dev_index not in cls._instances:
            cls._instances[dev_index] = cls(dev_index)
        return cls._instances[dev_index]

    def __init__(self, dev_index: int = 0) -> None:
        self.dev_index = dev_index
        self.dll: ctypes.CDLL | None = None
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self._ref_count = 0
        self._is_open = False

    def _get_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if self._lock is None or (self._lock_loop is not None and self._lock_loop.is_closed()):
            self._lock = asyncio.Lock()
            self._lock_loop = current_loop
        return self._lock

    @property
    def is_open(self) -> bool:
        return self._is_open

    async def open(self) -> None:
        if self._is_open:
            self._ref_count += 1
            return

        dll = _load_ch347_dll()
        if not dll:
            dll_name = "CH347DLLA64.DLL" if sys.maxsize > 2**32 else "CH347DLL.DLL"
            raise CDllMissingError(
                dll_name,
                hint="Please ensure WCH CH347 driver/DLL is available. Run C:\\WCH.CN\\CH341PAR\\SETUP.EXE.",
            )

        loop = asyncio.get_running_loop()
        handle = await loop.run_in_executor(None, dll.CH347OpenDevice, self.dev_index)

        # 校验句柄是否有效 (INVALID_HANDLE_VALUE)
        if handle in (-1, 0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF):
            raise ConnectionError(
                f"Failed to open CH347 hardware device (index={self.dev_index}).\n"
                "Troubleshooting steps:\n"
                "1. Check if WCH CH341PAR driver is installed: https://www.wch.cn/downloads/CH341PAR_EXE.html\n"
                "2. Ensure hardware mode pins (DTR1/RTS1) are set to Mode 1 (I2C+SPI+UART+GPIO)\n"
                "3. Ensure USB cable is securely connected and not in use by another application."
            )

        self.dll = dll
        self._is_open = True
        self._ref_count = 1

    async def close(self, force: bool = False) -> None:
        if not self._is_open:
            return
        if not force:
            self._ref_count -= 1
            if self._ref_count > 0:
                return

        self._is_open = False
        self._ref_count = 0
        if self.dll is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.dll.CH347CloseDevice, self.dev_index)
            self.dll = None

    def i2c(self, frequency: int = 400_000, **kwargs: Any) -> Ch347I2cTransport:
        return Ch347I2cTransport(self, frequency=frequency, borrowed=True, **kwargs)

    def spi(self, cs: int = 0, frequency: int = 15_000_000, mode: int = 0, **kwargs: Any) -> Ch347SpiTransport:
        return Ch347SpiTransport(self, cs=cs, frequency=frequency, mode=mode, borrowed=True, **kwargs)

    def gpio(self, pin: int = 0, **kwargs: Any) -> Ch347GpioPin:
        return Ch347GpioPin(self, pin=pin, **kwargs)

# --- 顶层物理底座传输抽象 (供 cio.connect("ch347://0") 使用) ---

class Ch347DeviceTransport(AsyncBaseTransport):
    """
    Top-level transport wrapper for CH347 physical baseboard.
    Provides i2c(), spi(), and gpio() channel derivation.
    """
    def __init__(
        self,
        address: str = "0",
        index: int | str = 0,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        trace: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        idx_str = str(address).strip("/") if address else str(index)
        self.dev_index = parse_int(idx_str, default=0)
        self.device = Ch347Device.get_or_create(self.dev_index)

    @property
    def is_open(self) -> bool:
        return self.device.is_open

    async def open(self) -> None:
        await self.device.open()
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False
        await self.device.close(force=True)

    def i2c(self, frequency: int = 400_000, **kwargs: Any) -> Ch347I2cTransport:
        return self.device.i2c(frequency=frequency, **kwargs)

    def spi(self, cs: int = 0, frequency: int = 15_000_000, mode: int = 0, **kwargs: Any) -> Ch347SpiTransport:
        return self.device.spi(cs=cs, frequency=frequency, mode=mode, **kwargs)

    def gpio(self, pin: int = 0, **kwargs: Any) -> Ch347GpioPin:
        return self.device.gpio(pin=pin, **kwargs)

    async def _write_impl(self, data: bytes) -> int:
        raise NotImplementedError("CH347 base transport is a composite container; use i2c/spi/gpio/serial channels.")

    async def _read_impl(self, nbytes: int) -> bytes:
        raise NotImplementedError("CH347 base transport is a composite container; use i2c/spi/gpio/serial channels.")

# --- I2C 总线传输实现 ---

class Ch347I2cTransport(AsyncI2cTransport):
    """
    Hardware I2C Master Transport using CH347 C API.
    """
    def __init__(
        self,
        device: Ch347Device | int = 0,
        frequency: int = 400_000,
        reg_len: int = 1,
        borrowed: bool = False,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        trace: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, reg_len=reg_len, trace=trace)
        if isinstance(device, int):
            self.device = Ch347Device.get_or_create(device)
        else:
            self.device = device
        self.frequency = int(frequency)
        self._borrowed = borrowed

    @property
    def is_open(self) -> bool:
        return self.device.is_open and self._is_open

    async def open(self) -> None:
        if self._is_open:
            return
        await self.device.open()

        # 映射频率到 CH347 速率模式: 0=20KHz, 1=100KHz, 2=400KHz, 3=750KHz
        if self.frequency <= 20_000:
            speed_mode = 0
        elif self.frequency <= 100_000:
            speed_mode = 1
        elif self.frequency <= 400_000:
            speed_mode = 2
        else:
            speed_mode = 3

        loop = asyncio.get_running_loop()
        assert self.device.dll is not None
        ok = await loop.run_in_executor(None, self.device.dll.CH347I2C_Set, self.device.dev_index, speed_mode)
        if not ok:
            raise IOOperationError(f"Failed to set CH347 I2C speed to {self.frequency}Hz")
        self._is_open = True

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if not self._borrowed:
            await self.device.close()

    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        if not self._is_open:
            await self.open()
        assert self.device.dll is not None

        # I2C 读操作：写入从机读地址 (addr << 1 | 0x01)，读取 nbytes
        write_addr = bytes([(addr << 1) | 0x01])
        read_buf = (ctypes.c_ubyte * nbytes)()
        loop = asyncio.get_running_loop()

        async with self.device._get_lock():
            ok = await loop.run_in_executor(
                None,
                self.device.dll.CH347StreamI2C,
                self.device.dev_index,
                1,
                write_addr,
                nbytes,
                read_buf,
            )
            if not ok:
                raise IOOperationError(f"CH347 I2C read from address 0x{addr:02X} failed")
            data = bytes(read_buf)
            self.logger.log_in(data, tag="I2C-RX")
            return data

    async def write(self, addr: int, data: BytesLike, timeout: float | None = None) -> int:
        if not self._is_open:
            await self.open()
        assert self.device.dll is not None

        raw = ensure_bytes(data)
        # I2C 写操作：写入从机写地址 (addr << 1 & 0xFE) + 数据负载
        wbuf = bytes([(addr << 1) & 0xFE]) + raw
        loop = asyncio.get_running_loop()

        async with self.device._get_lock():
            self.logger.log_out(raw, tag="I2C-TX")
            ok = await loop.run_in_executor(
                None,
                self.device.dll.CH347StreamI2C,
                self.device.dev_index,
                len(wbuf),
                wbuf,
                0,
                None,
            )
            if not ok:
                raise IOOperationError(f"CH347 I2C write to address 0x{addr:02X} failed")
            return len(raw)

    async def read_reg(
        self,
        addr: int,
        reg: int,
        nbytes: int = 1,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """
        Hardware-optimized atomic Repeated-Start register read via single CH347StreamI2C transaction.
        """
        if not self._is_open:
            await self.open()
        assert self.device.dll is not None

        needed_len = (reg.bit_length() + 7) // 8 or 1
        base_len = reg_len if reg_len is not None else self.default_reg_len
        actual_reg_len = max(base_len, needed_len) if reg_len is None else reg_len
        reg_bytes = reg.to_bytes(actual_reg_len, byteorder="big")

        # 原子操作：写地址+寄存器，硬件无缝发送 Repeated Start 紧随读取
        wbuf = bytes([(addr << 1) & 0xFE]) + reg_bytes
        read_buf = (ctypes.c_ubyte * nbytes)()
        loop = asyncio.get_running_loop()

        async with self.device._get_lock():
            ok = await loop.run_in_executor(
                None,
                self.device.dll.CH347StreamI2C,
                self.device.dev_index,
                len(wbuf),
                wbuf,
                nbytes,
                read_buf,
            )
            if not ok:
                raise IOOperationError(f"CH347 atomic read_reg failed (addr=0x{addr:02X}, reg=0x{reg:04X})")
            data = bytes(read_buf)
            self.logger.log_in(data, tag="I2C-REG-RX")
            return data

    async def scan(self, timeout: float | None = None) -> list[int]:
        """
        Scan I2C bus for responsive 7-bit slave addresses (0x08 to 0x77).
        Uses native hardware 1-byte standard address probe (START -> [addr_W] -> ACK -> STOP).
        """
        if not self._is_open:
            await self.open()
        assert self.device.dll is not None

        active_addresses: list[int] = []
        loop = asyncio.get_running_loop()
        dll = self.device.dll
        idx = self.device.dev_index

        has_raw_io = hasattr(dll, "CH347WriteData") and hasattr(dll, "CH347ReadData")

        async with self.device._get_lock():
            if has_raw_io:
                # 沁恒底层原生单字节 I2C 探测协议包 (规范级无侵入单字节嗅探):
                # 0xAA(STREAM) + 0x74(STA) + 0x80(0长度OUT:仅发送1字节地址并返回ACK状态) + Addr_W + 0x75(STO) + 0x00(END)
                for addr in range(0x08, 0x78):
                    raw_cmd = bytes([0xAA, 0x74, 0x80, (addr << 1) & 0xFE, 0x75, 0x00])
                    wlen = ctypes.c_ulong(len(raw_cmd))
                    ok_w = await loop.run_in_executor(None, dll.CH347WriteData, idx, raw_cmd, ctypes.byref(wlen))
                    if not ok_w:
                        continue
                    rbuf = (ctypes.c_ubyte * 8)()
                    rlen = ctypes.c_ulong(8)
                    ok_r = await loop.run_in_executor(None, dll.CH347ReadData, idx, rbuf, ctypes.byref(rlen))
                    if ok_r and rlen.value > 0 and (rbuf[0] & 0x01):
                        active_addresses.append(addr)
            elif hasattr(dll, "CH347StreamI2C_RetACK"):
                for addr in range(0x08, 0x78):
                    wbuf = bytes([(addr << 1) & 0xFE, 0x00])
                    ack_cnt = ctypes.c_ulong(0)
                    ok = await loop.run_in_executor(
                        None,
                        dll.CH347StreamI2C_RetACK,
                        idx,
                        len(wbuf),
                        wbuf,
                        0,
                        None,
                        ctypes.byref(ack_cnt),
                    )
                    if ok and ack_cnt.value >= 1:
                        active_addresses.append(addr)
            else:
                for addr in range(0x08, 0x78):
                    wbuf = bytes([(addr << 1) & 0xFE, 0x00])
                    ok = await loop.run_in_executor(
                        None,
                        dll.CH347StreamI2C,
                        idx,
                        len(wbuf),
                        wbuf,
                        0,
                        None,
                    )
                    if ok:
                        active_addresses.append(addr)
        return active_addresses

# --- SPI 总线传输实现 ---

class Ch347SpiTransport(AsyncSpiTransport):
    """
    Hardware SPI Master Transport using CH347 C API.
    """
    def __init__(
        self,
        device: Ch347Device | int = 0,
        cs: int = 0,
        frequency: int = 15_000_000,
        mode: int = 0,
        borrowed: bool = False,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        trace: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        if isinstance(device, int):
            self.device = Ch347Device.get_or_create(device)
        else:
            self.device = device
        self.cs = int(cs)
        self.frequency = int(frequency)
        self.mode = int(mode)
        self._borrowed = borrowed

    @property
    def is_open(self) -> bool:
        return self.device.is_open and self._is_open

    async def open(self) -> None:
        if self._is_open:
            return
        await self.device.open()

        # 时钟分频映射: 0=60M, 1=30M, 2=15M, 3=7.5M, 4=3.75M, 5=1.875M, 6=937.5K, 7=468.75K
        freq = self.frequency
        if freq >= 60_000_000:
            clock_div = 0
        elif freq >= 30_000_000:
            clock_div = 1
        elif freq >= 15_000_000:
            clock_div = 2
        elif freq >= 7_500_000:
            clock_div = 3
        elif freq >= 3_750_000:
            clock_div = 4
        elif freq >= 1_875_000:
            clock_div = 5
        elif freq >= 937_500:
            clock_div = 6
        else:
            clock_div = 7

        cfg = mSpiCfgS()
        cfg.iMode = self.mode & 0x03
        cfg.iClock = clock_div
        cfg.iByteOrder = 1               # MSB First
        cfg.iSpiWriteReadInterval = 0
        cfg.iSpiOutDefaultData = 0xFF
        cfg.iChipSelect = 0x80 | (1 << self.cs)  # 硬件片选使能
        cfg.CS1Polarity = 0             # 低有效
        cfg.CS2Polarity = 0
        cfg.iIsAutoDeativeCS = 1         # 传输后自动拉高释放
        cfg.iActiveDelay = 0
        cfg.iDelayDeactive = 0

        loop = asyncio.get_running_loop()
        assert self.device.dll is not None
        ok = await loop.run_in_executor(None, self.device.dll.CH347SPI_Init, self.device.dev_index, ctypes.byref(cfg))
        if not ok:
            raise IOOperationError(f"Failed to initialize CH347 SPI (mode={self.mode}, freq={self.frequency})")
        self._is_open = True

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if not self._borrowed:
            await self.device.close()

    async def transfer(self, tx_data: BytesLike, timeout: float | None = None) -> bytes:
        if not self._is_open:
            await self.open()
        assert self.device.dll is not None

        raw_tx = ensure_bytes(tx_data)
        length = len(raw_tx)
        if length == 0:
            return b""

        # 全双工缓冲区
        io_buf = (ctypes.c_ubyte * length).from_buffer_copy(raw_tx)
        cs_mask = 0x80 | (1 << self.cs)
        loop = asyncio.get_running_loop()

        async with self.device._get_lock():
            self.logger.log_out(raw_tx, tag="SPI-TX")
            ok = await loop.run_in_executor(
                None,
                self.device.dll.CH347SPI_WriteRead,
                self.device.dev_index,
                cs_mask,
                length,
                io_buf,
            )
            if not ok:
                raise IOOperationError(f"CH347 SPI transfer of {length} bytes failed")
            rx_data = bytes(io_buf)
            self.logger.log_in(rx_data, tag="SPI-RX")
            return rx_data

# --- GPIO 控制引脚实现 ---

class Ch347GpioPin(AsyncGpioPin):
    """
    Hardware GPIO Pin Control using CH347 C API.
    """
    def __init__(self, device: Ch347Device | int = 0, pin: int = 0, borrowed: bool = True, **kwargs: Any) -> None:
        super().__init__()
        if isinstance(device, int):
            self.device = Ch347Device.get_or_create(device)
        else:
            self.device = device
        self.pin = int(pin)
        self._state = False
        self._borrowed = borrowed
        self._is_open = False

    @property
    def is_open(self) -> bool:
        return self.device.is_open and self._is_open

    async def open(self) -> None:
        if self._is_open:
            return
        await self.device.open()
        self._is_open = True

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if not self._borrowed:
            await self.device.close()

    async def set_high(self) -> None:
        if not self.device.is_open:
            await self.device.open()
        assert self.device.dll is not None

        loop = asyncio.get_running_loop()
        mask = 1 << self.pin
        async with self.device._get_lock():
            # iEnable=mask, iSetDirOut=mask (输出方向), iSetDataOut=mask (高电平)
            ok = await loop.run_in_executor(None, self.device.dll.CH347GPIO_Set, self.device.dev_index, mask, mask, mask)
            if not ok:
                raise IOOperationError(f"Failed to set CH347 GPIO pin {self.pin} HIGH")
            self._state = True

    async def set_low(self) -> None:
        if not self.device.is_open:
            await self.device.open()
        assert self.device.dll is not None

        loop = asyncio.get_running_loop()
        mask = 1 << self.pin
        async with self.device._get_lock():
            # iEnable=mask, iSetDirOut=mask (输出方向), iSetDataOut=0 (低电平)
            ok = await loop.run_in_executor(None, self.device.dll.CH347GPIO_Set, self.device.dev_index, mask, mask, 0)
            if not ok:
                raise IOOperationError(f"Failed to set CH347 GPIO pin {self.pin} LOW")
            self._state = False

    async def toggle(self) -> None:
        if self._state:
            await self.set_low()
        else:
            await self.set_high()

    async def read_level(self) -> bool:
        if not self.device.is_open:
            await self.device.open()
        assert self.device.dll is not None

        loop = asyncio.get_running_loop()
        dir_val = ctypes.c_ubyte(0)
        data_val = ctypes.c_ubyte(0)

        async with self.device._get_lock():
            ok = await loop.run_in_executor(
                None,
                self.device.dll.CH347GPIO_Get,
                self.device.dev_index,
                ctypes.byref(dir_val),
                ctypes.byref(data_val),
            )
            if not ok:
                raise IOOperationError(f"Failed to read CH347 GPIO pin {self.pin} level")
            self._state = bool((data_val.value >> self.pin) & 0x01)
            return self._state

    async def wait_for_edge(
        self,
        edge: Literal["rising", "falling", "both"] = "rising",
        timeout: float | None = None,
    ) -> bool:
        initial = await self.read_level()
        start = asyncio.get_running_loop().time()
        while True:
            await asyncio.sleep(0.01)
            current = await self.read_level()
            if initial != current:
                prev = initial
                initial = current
                if edge == "rising" and not prev and current:
                    return True
                elif edge == "falling" and prev and not current:
                    return True
                elif edge == "both":
                    return True
            if timeout is not None and (asyncio.get_running_loop().time() - start) >= timeout:
                return False

# --- 注册进入 cio.core.registry ---

registry.register(
    name="ch347",
    schemes=["ch347"],
    factory_cls=Ch347DeviceTransport,
    probe_fn=_probe_ch347,
    scan_fn=_scan_ch347,
)
