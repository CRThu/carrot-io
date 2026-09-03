"""
单底座多协议多路复用示例 (I2C + GPIO 共用单一串口物理底座)

适用场景:
当一块下位机板子 (如 CarrotBridge) 通过同一个串口连接到电脑，
但板子上同时引出了 I2C 总线与 GPIO 复位引脚时，
通过物理底座直接派生逻辑信道，底层自动共享串口句柄并具备事务互斥排他保护。
"""
import asyncio
import cio


async def async_demo():
    # 1. 打开单一物理串口底座 (物理 Owner，串口在进程中只打开一次)
    # 实际硬件可使用: bridge = cio.connect("serial://COM3?baud=2000000")
    bridge = cio.connect("tcp://127.0.0.1:5025")

    # 2. 从底座直接派生子协议通道 (借用模式 borrowed=True)
    i2c = bridge.i2c(bus=0, reg_len=2)
    rst_pin = bridge.gpio(pin=1)

    try:
        # 3. 通过 GPIO 对从机芯片执行硬件复位
        print("[GPIO] 拉低芯片复位引脚...")
        await rst_pin.set_low()
        await asyncio.sleep(0.05)
        print("[GPIO] 释放芯片复位引脚...")
        await rst_pin.set_high()

        # 4. 通过 I2C 访问芯片寄存器
        print("[I2C] 写入配置寄存器...")
        await i2c.write_reg(addr=0x57, reg=0xFFB6, data=0xFF)

        data = await i2c.read_reg(addr=0x57, reg=0xFFB0, nbytes=1)
        print(f"[I2C] 读取状态寄存器: 0x{data.hex()}")

        # 5. 关闭借用信道: 仅注销 I2C 逻辑状态，底层串口依然保持连接！
        await i2c.close()
        print("[I2C] 信道已关闭，底层底座依然保持通信！")

        # 6. GPIO 依旧可正常通信
        level = await rst_pin.read_level()
        print(f"[GPIO] 当前引脚电平: {level}")

    finally:
        # 7. 测试流程全部结束，关闭物理底座
        await bridge.close()
        print("[Bridge] 物理底座已彻底释放。")


def sync_demo():
    """同步测试调用风格"""
    # with bridge 自动进入同步包装视图
    with cio.connect("serial://COM3?baud=2000000") as bridge:
        rst_pin = bridge.gpio(pin=1)
        i2c = bridge.i2c(bus=0, reg_len=2)

        # 复位操作
        with rst_pin as pin:
            pin.set_low()
            pin.set_high()

        # I2C 操作
        with i2c as dev:
            dev.write_reg(0x57, 0xFFB6, 0xFF)
            status = dev.read_reg(0x57, 0xFFB0, 1)
            print("Status:", status.hex())


if __name__ == "__main__":
    asyncio.run(async_demo())
