"""
硬件底座多路复用教学示例 (单串口同时借用 I2C 与 GPIO)

适用场景:
下位机通过同一个串口连接，板上同时引出 I2C 总线与 GPIO 复位引脚。
从底座借用 (borrow) 派生子信道，底层串口句柄共享并具备原子事务锁保护。
"""
import asyncio
import cio

URL = "serial://COM3?baud=115200"


# 1. 异步原生模式 (推荐)
async def async_demo():
    # 打开单一物理串口底座 (持有实际硬件连接)
    async with cio.connect(URL, timeout=2.0) as bridge:
        # 从底座派生 I2C 与 GPIO 逻辑信道 (借用模式)
        i2c = bridge.i2c(bus=0, reg_len=1)
        rst_pin = bridge.gpio(pin=1)

        # GPIO 硬件复位
        await rst_pin.set_low()
        await rst_pin.set_high()

        # I2C 读取芯片寄存器
        data = await i2c.read_reg(addr=0x57, reg=0x00, nbytes=1)
        print("I2C 读取寄存器:", data.hex())


# 2. 同步模式
def sync_demo():
    with cio.connect(URL, timeout=2.0) as bridge:
        rst_pin = bridge.gpio(pin=1)
        i2c = bridge.i2c(bus=0, reg_len=1)

        rst_pin.set_low()
        rst_pin.set_high()

        data = i2c.read_reg(0x57, 0x00, 1)
        print("I2C 读取寄存器:", data.hex())


if __name__ == "__main__":
    try:
        asyncio.run(async_demo())
        # sync_demo()
    except cio.TransportError as err:
        print("[多路复用提示] 硬件未连接或端口被占用:", err)
