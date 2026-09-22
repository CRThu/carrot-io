"""
UDP 数据包传输教学示例 (离散数据包收发)
"""
import asyncio
import cio

HOST = "127.0.0.1"
PORT = 5025


# 1. 异步原生模式 (推荐，纯协程高并发)
async def async_demo():
    async with cio.udp(HOST, port=PORT, timeout=2.0) as dev:
        # 发送离散 UDP 数据包
        await dev.write(b"PING")
        # 接收数据包
        packet = await dev.read()
        print("收到 UDP 数据包:", packet)


# 2. 同步模式 (线性测试脚本，零异步语法负担)
def sync_demo():
    with cio.udp(HOST, port=PORT, timeout=2.0) as dev:
        dev.write(b"PING")
        packet = dev.read()
        print("收到 UDP 数据包:", packet)


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        # sync_demo()
    except cio.TransportError as err:
        print("[UDP 提示] 通信超时或异常:", err)
