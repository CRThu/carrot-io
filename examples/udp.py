"""
UDP 报文传输示例
"""
import asyncio
import cio


async def main():
    try:
        # async with cio.connect("udp://127.0.0.1:5025", timeout=2.0) as dev:
        async with cio.udp("127.0.0.1", port=5025, timeout=2.0) as dev:
            await dev.write_packet(b"\x01\x02\x03\x04")
            packet = await dev.read_packet()
            print("收到 UDP 数据包:", packet)
    except cio.ReadTimeoutError:
        print("[超时提示] 未收到 UDP 数据包响应")
    except cio.TransportError as e:
        print("[传输提示] 通信异常:", e)


if __name__ == "__main__":
    asyncio.run(main())
