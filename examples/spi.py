"""
SPI 总线通信示例 (SPI Master)
"""
import asyncio
import cio


async def main():
    try:
        # 支持通过 SPI+TCP 或 SPI+Serial 组合 URL 连接下位机 SPI 桥
        async with cio.connect("spi+tcp://192.168.1.100:5025?clock=10MHz", timeout=2.0) as spi:
            # 1. 发送 JEDEC ID 读取指令 (0x9F) 并读取 3 字节响应
            rx = await spi.transfer(b"\x9F\x00\x00\x00")
            print(f"读取到的 Flash JEDEC ID: {rx.hex()}")

            # 2. 单向写入数据 (丢弃 MISO)
            await spi.write(b"\x06")  # 写使能 (WREN)

            # 3. 单向读取数据 (发送 Dummy 字节)
            status = await spi.read(1)
            print(f"Flash 状态寄存器: {status.hex()}")
    except cio.TransportError as e:
        print("[SPI 提示] 通信或设备未响应:", e)


if __name__ == "__main__":
    asyncio.run(main())
