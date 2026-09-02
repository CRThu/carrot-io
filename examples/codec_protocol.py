"""
工业二进制与文本帧编解码协议绑定示例 (FramedBinaryCodec & LineCodec)
"""
import asyncio
import cio
from cio import FramedBinaryCodec, LineCodec, MockTransport


async def main():
    # 使用 Mock 设备模拟下位机二进制数据流
    mock_dev = MockTransport()
    
    # 1. 绑定定界符文本协议 (如 SCPI 仪器协议)
    line_proto = mock_dev.bind(LineCodec(delimiter=b"\n"))
    mock_dev.add_auto_reply(b"*IDN?\n", b"CARROT_DMM_V1.0\n")

    async with line_proto:
        resp = await line_proto.query("*IDN?")
        print("SCPI 响应:", resp)

    # 2. 绑定标准工业二进制帧: [HEADER 0xAA55][PAYLOAD_LEN 2B][PAYLOAD][CRC16]
    binary_codec = FramedBinaryCodec(header=b"\xAA\x55", crc_type="crc16")
    bin_proto = mock_dev.bind(binary_codec)

    async with bin_proto:
        # 发送业务载荷 (自动打包帧头、长度与 CRC16)
        await bin_proto.write(b"\x01\x03\x00\x00\x00\x02")
        print("最近发送的原始帧记录:")
        print(bin_proto.dump_history(limit=1, show_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
