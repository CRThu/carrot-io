"""
异步串口 (Async Serial) 通信示例
"""
import asyncio
import cio


async def main():
    try:
        # async with cio.connect("serial://COM6?baud=115200", timeout=1.0) as dev:
        async with cio.serial("COM6", baud=115200, timeout=1.0) as dev:
            await dev.write(b"HELLO\r\n")
            line = await dev.read_until(b"\n")
            print("读取到的数据:", line)
    except cio.TransportError as e:
        print("[串口提示] 打开或通信失败:", e)


if __name__ == "__main__":
    asyncio.run(main())
