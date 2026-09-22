"""
GPIO 引脚控制教学示例 (输出高低电平与输入读取)
"""
import asyncio
import cio

URL = "gpio://COM3?pin=1"


# 1. 异步原生模式 (推荐，纯协程驱动)
async def async_demo():
    async with cio.connect(URL, timeout=1.0) as pin:
        # 设置引脚电平
        await pin.set_high()
        print("设置高电平，当前读数:", await pin.read_level())

        await pin.set_low()
        print("设置低电平，当前读数:", await pin.read_level())


# 2. 同步模式 (线性测试脚本，零异步语法负担)
def sync_demo():
    with cio.connect(URL, timeout=1.0) as pin:
        pin.set_high()
        print("设置高电平，当前读数:", pin.read_level())

        pin.set_low()
        print("设置低电平，当前读数:", pin.read_level())


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        # sync_demo()
    except cio.TransportError as err:
        print("[GPIO 提示] 硬件未连接或端口被占用:", err)
