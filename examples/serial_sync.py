"""
同步串口 (Sync Serial) 通信示例
"""
import cio


def main():
    try:
        # with cio.connect("serial://COM6?baud=115200", timeout=1.0).sync as dev:
        with cio.serial("COM6", baud=115200, timeout=1.0).sync as dev:
            dev.write(b"HELLO\r\n")
            data = dev.read(10)
            print("读取到的数据:", data)
    except cio.TransportError as e:
        print("[串口提示] 打开或通信失败:", e)


if __name__ == "__main__":
    main()
