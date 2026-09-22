"""
VISA 示波器/工业仪表通信教学示例 (SCPI 控制)
"""
import asyncio
import cio

# VISA 资源名 (可通过 cio.scan("visa") 自动发现)
RESOURCE = "USB0::0x2A8D::0x9007::MY63160152::INSTR"


# 1. 异步原生模式 (推荐，纯协程高并发)
async def async_demo():
    async with cio.visa(RESOURCE, timeout=3.0) as scope:
        # 查询设备标识 (自动解码并剔除末尾换行)
        idn = await scope.query("*IDN?")
        print("设备标识 (IDN):", idn)

        # 发送 SCPI 配置指令 (自动补换行)
        await scope.write("*CLS")


# 2. 同步模式 (常规测试脚本，零异步语法负担)
def sync_demo():
    with cio.visa(RESOURCE, timeout=3.0) as scope:
        idn = scope.query("*IDN?")
        print("设备标识 (IDN):", idn)
        scope.write("*CLS")


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        # sync_demo()
    except cio.TransportError as err:
        print("[VISA 提示] 仪器未连接或驱动异常:", err)
