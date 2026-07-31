"""
Hardware Control Frame Protocol (HardwareFrame & FrameCodec).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cio.core.codec import BaseCodec
from cio.core.exceptions import FrameChecksumError

# Peripheral Identifiers
PERIPHERAL_GPIO = 0x01
PERIPHERAL_I2C = 0x02
PERIPHERAL_SPI = 0x03

# Action Identifiers
ACTION_CFG = 0x00         # Configuration (Baudrate, Mode, Pull-up, etc.)
ACTION_READ_DATA = 0x01   # Direct Raw Data Read (read_from / read_packet)
ACTION_WRITE_DATA = 0x02  # Direct Raw Data Write (write_to / write_packet)
ACTION_TRANSFER = 0x03    # Full-Duplex Transfer (SPI transfer)
ACTION_READ_REG = 0x04    # Register Read with Regfile & Reg Addr (read_reg)
ACTION_WRITE_REG = 0x05   # Register Write with Regfile & Reg Addr (write_reg)



# Status Codes
STATUS_OK = 0x00
STATUS_NACK = 0x01
STATUS_BUSY = 0x02
STATUS_ERR = 0xFF

# Sub-Configuration Item IDs
CFG_GPIO_MODE = 0x01
CFG_GPIO_PULL = 0x02

CFG_I2C_SPEED = 0x01

CFG_SPI_MODE = 0x01
CFG_SPI_BIT_ORDER = 0x02
CFG_SPI_SPEED = 0x03


def _build_crc16_table() -> tuple[int, ...]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
        table.append(crc)
    return tuple(table)


_CRC16_TABLE = _build_crc16_table()


def calc_crc16_modbus(data: bytes | bytearray) -> int:
    """
    Calculate CRC16-MODBUS checksum for given bytes using zero-dependency 256-element LUT.
    Polynomial: 0xA001 (LSB first)
    Initial Value: 0xFFFF
    """
    crc = 0xFFFF
    for b in data:
        crc = (crc >> 8) ^ _CRC16_TABLE[(crc ^ b) & 0xFF]
    return crc



@dataclass
class HardwareFrame:
    """
    Hardware Control Frame Data Structure V1.0.
    """

    header: bytes = b"\x3C"  # '<'
    protocol: int = 0x10     # Protocol Version 1.0
    peripheral: int = PERIPHERAL_GPIO
    action: int = ACTION_CFG
    bus: int = 0x00
    addr: int = 0x00
    status: int = STATUS_OK
    payload: bytes = b""
    crc16: int | None = None
    tail: bytes = b"\x3E"    # '>'


class FrameCodec(BaseCodec):
    """
    Codec for Hardware Control Frame V1.0 Protocol.

    Frame Specification:
    Offset 0: HEADER (1 Byte, '<' / 0x3C)
    Offset 1: PROTOCOL (1 Byte, 0x10)
    Offset 2: PERIPHERAL (1 Byte, 0x01 GPIO, 0x02 I2C, 0x03 SPI)
    Offset 3: ACTION (1 Byte, 0x00 CFG, 0x01 READ, 0x02 WRITE, 0x03 TRANSFER)
    Offset 4: BUS (1 Byte, Pin ID, SPI CS Pin ID, I2C Bus ID)
    Offset 5: ADDR (1 Byte, I2C 7-bit slave address or 0x00)
    Offset 6: STATUS (1 Byte, 0x00 OK, 0x01 NACK, 0x02 BUSY, 0xFF ERR)
    Offset 7..8: PAYLOAD_LEN (2 Bytes, Big-Endian uint16)
    Offset 9..9+N-1: PAYLOAD (N Bytes)
    Offset 9+N..10+N: CRC16-MODBUS (2 Bytes, Little-Endian uint16)
    Offset 11+N: TAIL (1 Byte, '>' / 0x3E)
    """

    HEADER_BYTE = 0x3C  # '<'
    TAIL_BYTE = 0x3E    # '>'
    PROTOCOL_VERSION = 0x10
    HEADER_SIZE = 9
    FOOTER_SIZE = 3
    MIN_FRAME_SIZE = HEADER_SIZE + FOOTER_SIZE  # 12 Bytes

    def encode(self, message: HardwareFrame | Any) -> bytes:
        if not isinstance(message, HardwareFrame):
            raise TypeError(f"Expected HardwareFrame instance, got {type(message)}")

        payload = message.payload or b""
        payload_len = len(payload)

        # Build data bytes starting from PROTOCOL (Offset 1) up to end of PAYLOAD
        crc_data = bytes([
            message.protocol,
            message.peripheral,
            message.action,
            message.bus & 0xFF,
            message.addr & 0xFF,
            message.status & 0xFF,
            (payload_len >> 8) & 0xFF,
            payload_len & 0xFF,
        ]) + payload

        crc_val = calc_crc16_modbus(crc_data)
        crc_bytes = crc_val.to_bytes(2, byteorder="little")

        return bytes([self.HEADER_BYTE]) + crc_data + crc_bytes + bytes([self.TAIL_BYTE])

    def decode(self, buffer: bytearray) -> tuple[HardwareFrame | None, int]:
        if not buffer:
            return None, 0

        # Find HEADER byte
        idx = buffer.find(bytes([self.HEADER_BYTE]))
        if idx == -1:
            return None, len(buffer)

        if idx > 0:
            return None, idx

        if len(buffer) < self.MIN_FRAME_SIZE:
            return None, 0

        payload_len = (buffer[7] << 8) | buffer[8]
        frame_len = self.MIN_FRAME_SIZE + payload_len

        if len(buffer) < frame_len:
            return None, 0

        # Validate TAIL byte
        if buffer[frame_len - 1] != self.TAIL_BYTE:
            # Header found but tail invalid; discard header byte to seek next potential frame
            return None, 1

        # CRC Check (from PROTOCOL at Offset 1 to PAYLOAD end)
        crc_data = bytes(buffer[1 : 9 + payload_len])
        rx_crc = int.from_bytes(buffer[9 + payload_len : 11 + payload_len], byteorder="little")
        calc_crc = calc_crc16_modbus(crc_data)

        if rx_crc != calc_crc:
            raise FrameChecksumError(
                f"HardwareFrame CRC mismatch: expected 0x{calc_crc:04X}, got 0x{rx_crc:04X}"
            )

        frame = HardwareFrame(
            header=bytes([self.HEADER_BYTE]),
            protocol=buffer[1],
            peripheral=buffer[2],
            action=buffer[3],
            bus=buffer[4],
            addr=buffer[5],
            status=buffer[6],
            payload=bytes(buffer[9 : 9 + payload_len]),
            crc16=rx_crc,
            tail=bytes([self.TAIL_BYTE]),
        )

        return frame, frame_len
