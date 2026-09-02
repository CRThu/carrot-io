"""
硬件自动化断言与计分验证框架示例 (Verifier: check / require / verify)
"""
import sys
from cio import MockTransport, check, require, verify


def run_hardware_verification() -> bool:
    # 建立 Mock 硬件设备模拟寄存器状态
    mock = MockTransport()
    # 模拟返回芯片寄存器 0xFFB0 的上电初值 0x10
    mock.add_auto_reply(b"\x57\xFF\xB0", b"\x10")

    verify.reset()

    # 1. 软断言：校验失败记录到计分板，不阻断流程
    check(0x10, 0x10, name="STATUS(0xFFB0) == 0x10")
    check.mask(0x14, 0x10, mask=0x10, name="OP_MODE Bit4 Check")

    # 2. 强断言：关键前置条件失败立即抛异常阻断
    require.len([0x01, 0x02, 0x03, 0x04], 4, name="UID Length Check")
    require.not_none("ValidDeviceInstance", name="Device Discovery")

    # 3. 输出结构化 ASCII/ANSI 记分板与 PASS/FAIL 汇总
    return verify.summary()


if __name__ == "__main__":
    success = run_hardware_verification()
    sys.exit(0 if success else 1)
