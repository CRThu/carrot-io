"""
Keysight B2980 Series (B2985 / B2985B) Electrometer / High Resistance Meter Driver.
"""
from __future__ import annotations

from typing import Any

from cio.devices.base import BaseScpiDevice


class B2985(BaseScpiDevice):
    """
    Keysight B2985 / B2985B 高精度静电计 / 高阻计专属驱动。

    常用能力：
    - 微弱电流测量（0.01 fA ~ 20 mA）
    - 电压测量（1 µV ~ 20 V）
    - 高阻测量（至 10 PΩ）与电荷测量
    - 内置高压源输出（±0.001 V ~ ±1000 V）
    - 20 MΩ 限流防打火硬件安全保护 (RLIM)
    """

    @staticmethod
    def _parse_val(raw: str) -> float:
        """从 SCPI 回包中提取首个浮点值，并对 9.91E37 溢出值归一化为 NaN。"""
        token = raw.split(",")[0].strip()
        val = float(token)
        return float("nan") if abs(val) >= 9.9e37 else val

    # -------------------------------------------------------------
    # 常用测量接口 (Sense)
    # -------------------------------------------------------------

    async def measure_current(self) -> float:
        """测量电流（单位：A）。"""
        return self._parse_val(await self.query(":MEAS:CURR?"))

    async def measure_voltage(self) -> float:
        """测量电压（单位：V）。"""
        return self._parse_val(await self.query(":MEAS:VOLT?"))

    async def measure_resistance(self) -> float:
        """测量电阻（单位：Ω）。"""
        return self._parse_val(await self.query(":MEAS:RES?"))

    async def measure_charge(self) -> float:
        """测量电荷量（单位：C）。"""
        return self._parse_val(await self.query(":MEAS:CHAR?"))

    async def measure(self) -> float:
        """触发当前主功能单次测量。"""
        return self._parse_val(await self.query(":MEAS?"))

    async def set_auto_range(self, enable: bool = True, func: str = "CURR") -> None:
        """配置自动量程开关 (:SENS:{func}:RANG:AUTO ON/OFF)。"""
        state = "ON" if enable else "OFF"
        await self.write(f":SENS:{func.upper().strip()}:RANG:AUTO {state}")

    async def set_nplc(self, nplc: float = 1.0, func: str = "CURR") -> None:
        """设置积分时间周期（0.001 ~ 100 PLC，用于工频噪声抑制）。"""
        await self.write(f":SENS:{func.upper().strip()}:NPLC {nplc}")

    async def set_zero_correct(self, enable: bool = True) -> None:
        """开启或关闭微电流零点校准 (:INP:ZCOR:STAT 1/0)。"""
        await self.write(f":INP:ZCOR:STAT {'1' if enable else '0'}")

    # -------------------------------------------------------------
    # 常用电压源与硬件保护接口 (Source & Protection)
    # -------------------------------------------------------------

    async def source_voltage(
        self,
        volts: float,
        output: bool | None = None,
        protection: bool | None = None,
    ) -> None:
        """
        设置电压源输出电压（单位：V）。
        遵循高压源安全时序：若请求关闭输出则先关断，若请求开启输出则配好电压/保护后再闭合。

        :param volts: 设定电压值 (-1000V ~ +1000V)。
        :param output: 可选同时配置输出开关 (True 开启 / False 关闭)。
        :param protection: 可选同时配置 20 MΩ 限流保护电阻开关 (True 启用 / False 禁用)。
        """
        if output is False:
            await self.set_output(False)
        if protection is not None:
            await self.set_protection(protection)
        await self.write(f":SOUR:VOLT {volts}")
        if output is True:
            await self.set_output(True)

    async def get_source_voltage(self) -> float:
        """读取当前电压源设定值（单位：V）。"""
        return float(await self.query(":SOUR:VOLT?"))

    async def set_output(self, enable: bool) -> None:
        """开启或关闭电压源输出开关 (:OUTP ON/OFF)。"""
        await self.write(f":OUTP {'ON' if enable else 'OFF'}")

    async def get_output(self) -> bool:
        """查询电压源输出开关状态。"""
        return (await self.query(":OUTP?")).strip() in {"1", "ON"}

    async def set_protection(self, enable: bool = True) -> None:
        """
        开启/关闭内置 20 MΩ 串联安全限流保护电阻 (RLIM)。
        注意：硬件要求更改保护电阻前输出继电器必须处于关闭状态。若输出处于开启状态，内部会自动进行无损安全切换。
        """
        was_on = await self.get_output()
        if was_on:
            await self.set_output(False)
        await self.write(f":SOUR:VOLT:RLIM:STAT {'ON' if enable else 'OFF'}")
        if was_on:
            await self.set_output(True)

    async def get_protection(self) -> bool:
        """查询 20 MΩ 限流保护电阻开关状态。"""
        return (await self.query(":SOUR:VOLT:RLIM:STAT?")).strip() in {"1", "ON"}
