"""
TCP Socket 传输教学示例 (网络 SCPI / 仪表通信)
"""
import asyncio
import cio

HOST = "127.0.0.1"
PORT = 5025


# 1. 异步原生模式 (推荐，纯协程高并发)
async def async_demo():
    async with cio.tcp(HOST, port=PORT, timeout=2.0) as dev:
        # 一问一答式查询
        resp = await dev.query(b"*IDN?\n")
        print("收到响应:", resp)


# 2. 同步模式 (线性测试脚本，零异步语法负担)
def sync_demo():
    with cio.tcp(HOST, port=PORT, timeout=2.0) as dev:
        resp = dev.query(b"*IDN?\n")
        print("收到响应:", resp)


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        # sync_demo()
    except cio.TransportError as err:
        print("[TCP 提示] 通信异常或网络不可达:", err)
