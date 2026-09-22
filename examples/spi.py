"""
SPI 总线最简教学示例 (SPI Master)

直连下位机或测试底座，全双工读取 SPI Flash JEDEC ID：
- 异步原生模式 (asyncio)
- 便捷同步模式 (with 上下文)
"""
import asyncio
import cio

URL = "spi://COM3?baud=2000000&cs=0"


# ==========================================
# 1. 异步模式 (原生协程)
# ==========================================
async def async_demo():
    print("--- 1. 原生异步模式 (Async) ---")
    async with cio.connect(URL, timeout=2.0) as spi:
        # 发送 0x9F 命令同时读回 3 字节厂商与设备 ID
        rx = await spi.transfer([0x9F, 0x00, 0x00, 0x00])
        print("Flash ID (原始回包):", rx.hex())


# ==========================================
# 2. 同步模式 (线性脚本，零异步语法心智负担)
# ==========================================
def sync_demo():
    print("\n--- 2. 便捷同步模式 (Sync) ---")
    with cio.connect(URL, timeout=2.0) as spi:
        rx = spi.transfer([0x9F, 0x00, 0x00, 0x00])
        print("Flash ID (原始回包):", rx.hex())


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        sync_demo()
    except cio.TransportError as err:
        print("[SPI 提示] 硬件未连接或端口被占用:", err)
