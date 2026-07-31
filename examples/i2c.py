"""
I2C 总线通信示例 (I2C Master)
"""
import asyncio
import cio


async def main():
    try:
        # async with cio.connect("i2c+serial://COM6?baud=115200", timeout=1.0) as dev:
        async with cio.connect("i2c+tcp://192.168.1.100:5025", timeout=2.0) as dev:
            # 设备 7 位 I2C 从机地址 (如 0x68 陀螺仪 / 传感器)
            i2c_addr = 0x68

            # 1. 寄存器读写 (写寄存器 0x6B 唤醒设备)
            await dev.write_reg(i2c_addr, reg=0x6B, data=b"\x00")

            # 2. 从寄存器 0x75 读取 1 字节 WHO_AM_I 芯片 ID
            chip_id = await dev.read_reg(i2c_addr, reg=0x75, nbytes=1)
            print(f"读取到的芯片 ID: {chip_id.hex()}")

            # 3. 从从机地址直接读取 6 字节数据
            data = await dev.read_from(i2c_addr, nbytes=6)
            print(f"读取到的原始数据 ({len(data)} 字节): {data.hex()}")
    except cio.TransportError as e:
        print("[I2C 提示] 通信或设备未响应:", e)


if __name__ == "__main__":
    asyncio.run(main())
