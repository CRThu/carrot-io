"""
I2C 总线最简教学示例 (I2C Master)

直连下位机或测试底座 (默认串口链路)，完成从机扫描与芯片寄存器读写：
- 异步原生模式 (asyncio)
- 便捷同步模式 (with 上下文)
"""
import asyncio
import cio

URL = "i2c://COM3?baud=115200"
SLAVE_ADDR = 0x68  # 7 位从机地址 (如陀螺仪/传感器/EEPROM)


# ==========================================
# 1. 异步模式 (原生协程)
# ==========================================
async def async_demo():
    print("--- 1. 原生异步模式 (Async) ---")
    async with cio.connect(URL, timeout=2.0) as i2c:
        # 扫描在线从机
        slaves = await i2c.scan()
        print("在线从机地址:", [hex(s) for s in slaves])

        # 写寄存器 (唤醒设备)
        await i2c.write_reg(SLAVE_ADDR, reg=0x6B, data=0x00)

        # 读寄存器 (读取 1 字节芯片 ID)
        chip_id = await i2c.read_reg(SLAVE_ADDR, reg=0x75, nbytes=1)
        print("芯片 ID:", chip_id.hex())


# ==========================================
# 2. 同步模式 (线性脚本，零异步语法心智负担)
# ==========================================
def sync_demo():
    print("\n--- 2. 便捷同步模式 (Sync) ---")
    with cio.connect(URL, timeout=2.0) as i2c:
        slaves = i2c.scan()
        print("在线从机地址:", [hex(s) for s in slaves])

        chip_id = i2c.read_reg(SLAVE_ADDR, reg=0x75, nbytes=1)
        print("芯片 ID:", chip_id.hex())


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        sync_demo()
    except cio.TransportError as err:
        print("[I2C 提示] 硬件未连接或端口被占用:", err)
