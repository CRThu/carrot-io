"""
串口 (UART/Serial) 通信教学示例
"""
import asyncio
import cio

PORT = "COM3"
BAUD = 115200


# 1. 异步原生模式 (推荐，纯协程并发)
async def async_demo():
    async with cio.serial(PORT, baud=BAUD, timeout=1.0) as dev:
        # 发送数据
        await dev.write(b"HELLO\r\n")
        # 按定界符读取回包
        line = await dev.read_until(b"\n")
        print("异步读取:", line)


# 2. 同步模式 (线性测试脚本，零异步语法负担)
def sync_demo():
    with cio.serial(PORT, baud=BAUD, timeout=1.0) as dev:
        dev.write(b"HELLO\r\n")
        line = dev.read_until(b"\n")
        print("同步读取:", line)


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        # sync_demo()
    except cio.TransportError as err:
        print("[串口提示] 端口未连接或被占用:", err)
