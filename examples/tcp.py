"""
TCP Socket 传输示例
"""
import asyncio
import cio


async def main():
    try:
        # async with cio.connect("tcp://127.0.0.1:5025", timeout=2.0) as dev:
        async with cio.tcp("127.0.0.1", port=5025, timeout=2.0) as dev:
            await dev.write(b"*IDN?\n")
            response = await dev.read_until(b"\n")
            print("收到响应:", response)
    except cio.ConnectTimeoutError:
        print("[连接提示] TCP 连接超时 (目标端口未开放或网络不可达)")
    except cio.TransportError as e:
        print("[传输提示] 通信异常:", e)


if __name__ == "__main__":
    asyncio.run(main())
