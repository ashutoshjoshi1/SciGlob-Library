"""TETech1090 wire-protocol helpers (``#``-framed, CRC-16/XMODEM, float32 hex).

All wire constants and algorithms here are taken from the TE Technology
temperature-controller spec (``specs/tetech.md`` §4), which was mined from the
field-proven Blick suite (``blick_serial.py`` / ``blick_xfus.py``). Section
references in the comments point at that spec.

The TETech1090 differs fundamentally from TETech1/TETech2:

* frames are ``#``-framed with a fixed 6-char address/sequence field,
* the checksum is CRC-16/XMODEM (not the additive mod-256 checksum),
* values are IEEE-754 float32 rendered as 8 hex chars (not scaled integers),
* answers are terminated by CR (``\\r``) instead of ``^``.
"""

import struct

from sciglob.core.exceptions import CommunicationError

# -- framing constants (spec §4.1) -----------------------------------------

CONTROL_CHAR = "#"  # question control char (blick_serial.py:1692)
ANSWER_PREFIX = "!"  # answer control char (blick_serial.py:1693)
# Address (chars [1:3]) + sequence number (chars [3:7]); the field code always
# sends the six literal chars "000000" (blick_serial.py:1694).
ADDRESS = "000000"
END_CHAR = "\r"  # CR terminator for both question and answer (spec §2)
WIRE_TEXT = "latin-1"  # text encoding across the Blick suite (spec §2)
DEFAULT_BAUDRATE = 19200  # 1090 default (spec §2 / TE Tech TC-1090 datasheet)

# -- register/command catalog (spec §4.3, blick_serial.py:107-123) ---------
# Register pattern: "VS" = value-set, "?VR" = value-read; the middle 4 hex
# chars are the parameter id, trailing "01" is the instance/index suffix.

CMD_QUERY_DEVICE_TYPE = "?VR006401"  # param 100  -> identify handshake
CMD_SET_TEMP = "VS0BB801"  # param 3000 -> set target object temperature
CMD_GET_SETPOINT = "?VR0BB801"  # param 3000 -> get target object temperature
CMD_GET_OBJECT_TEMP = "?VR03E801"  # param 1000 -> object temperature (ReadOnly)
CMD_GET_SINK_TEMP = "?VR03E901"  # param 1001 -> sink temperature (ReadOnly)
CMD_ENABLE_OUTPUT = "VS07DA01"  # param 2010 -> enable/disable controller output
CMD_SET_KP = "VS0BC201"  # param 3010 -> proportional gain (Kp)
CMD_GET_KP = "?VR0BC201"  # param 3010 -> proportional gain (Kp)
CMD_SET_TI = "VS0BC301"  # param 3011 -> integral time (Ti)
CMD_GET_TI = "?VR0BC301"  # param 3011 -> integral time (Ti)
CMD_SET_KD = "VS0BC401"  # param 3012 -> derivative gain (Kd)


def crc16_xmodem(data: bytes) -> int:
    """CRC-16/XMODEM over ``data``.

    Parameters: poly 0x1021, init 0x0000, MSB-first, no input/output
    reflection, no final XOR (spec §4.2, verbatim from
    ``blick_xfus.py:856-869`` ``get_checksum_CRC_CCITT``).

    Args:
        data: Bytes to checksum.

    Returns:
        The 16-bit CRC as an int.
    """
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc_hex(text: str) -> str:
    """CRC-16/XMODEM of ``text`` (latin-1) as 4 uppercase hex chars (spec §4.1)."""
    return f"{crc16_xmodem(text.encode('latin-1')):04X}"


def float_to_hex8(value: float) -> str:
    """Encode an IEEE-754 float32 as 8 uppercase hex chars (spec §4.4).

    The float is packed little-endian, reinterpreted as a uint32 and printed
    big-endian on the wire (e.g. 20.0 -> ``41A00000``). Unlike the legacy
    Blick ``hex()[2:]`` (which drops leading zero nibbles — spec §4.4/§11),
    this is zero-padded to a full 8 chars.

    Args:
        value: Value to encode.

    Returns:
        8-character uppercase hex string.
    """
    u = struct.unpack("<I", struct.pack("<f", value))[0]
    return f"{u:08X}"


def hex8_to_float(payload: str) -> float:
    """Decode 8 hex chars as an IEEE-754 float32 (spec §4.4).

    Args:
        payload: 8-character hex string.

    Returns:
        The decoded float.
    """
    u = int(payload, 16)
    return float(struct.unpack("<f", struct.pack("<I", u))[0])


def int_hex(value: int) -> str:
    """Encode a plain 32-bit integer as 8 uppercase hex chars (spec §4.4).

    Used for the enable-output value (``dec2hex(1, 32)`` -> ``00000001``);
    this value is an integer, NOT a float32.
    """
    return f"{value & 0xFFFFFFFF:08X}"


def build_frame(payload: str) -> str:
    """Build a full ``#``-framed question (without the trailing CR).

    Frame = ``#`` + ``000000`` + ``payload`` + CRC, where the CRC is
    CRC-16/XMODEM computed over the whole frame body *including* the leading
    ``#`` and excluding the CRC/CR (spec §4.1:
    ``ss = iidd + addr + writecmd + thex``).

    Args:
        payload: The command payload (e.g. ``VS0BB80141A00000``).

    Returns:
        The frame string, ready to have the CR terminator appended.
    """
    body = CONTROL_CHAR + ADDRESS + payload
    return body + crc_hex(body)


def frame_crc(payload: str) -> str:
    """Return the 4-char CRC of the frame carrying ``payload`` (spec §4.1)."""
    return crc_hex(CONTROL_CHAR + ADDRESS + payload)


# Identify/handshake frame (spec §1, blick_params.py:267): "#000000?VR006401A912".
IDENTIFY_FRAME = build_frame(CMD_QUERY_DEVICE_TYPE)


def expected_set_answer(payload: str) -> str:
    """Expected exact answer to a SET question (spec §4.6).

    The device echoes ``!`` + address + *the question's CRC* — not a CRC of
    the answer text (``blick_serial.py:1719-1722, 2036-2037``).
    """
    return ANSWER_PREFIX + ADDRESS + frame_crc(payload)


def parse_get_answer(answer: str) -> float:
    """Validate and decode a GET answer frame into a float (spec §4.6).

    Answer layout: ``!`` + address(2) + seq(4) + payload(8 hex) + CRC(4) + CR.
    The CRC is computed over ``!`` + address + seq + payload
    (``blick_serial.py:2036-2039``).

    Args:
        answer: The answer string (CR already stripped).

    Returns:
        The decoded float32 payload.

    Raises:
        CommunicationError: On device error (``+`` in the frame), a malformed
            frame, or a CRC mismatch.
    """
    answer = answer.strip("\r\n")

    # Error short-circuit: any "+" means a device error frame (spec §4.6,
    # e.g. "!000000+05A7C4").
    if "+" in answer:
        raise CommunicationError(f"TETech1090 reported an error: {answer!r}")

    expected_prefix = ANSWER_PREFIX + ADDRESS
    if not answer.startswith(expected_prefix) or len(answer) != len(expected_prefix) + 8 + 4:
        raise CommunicationError(f"Malformed TETech1090 answer: {answer!r}")

    body = answer[:-4]
    received_crc = answer[-4:]
    if crc_hex(body).upper() != received_crc.upper():
        raise CommunicationError(
            f"TETech1090 answer CRC mismatch: expected {crc_hex(body)}, got {received_crc}"
        )

    payload = answer[len(expected_prefix) : -4]
    return hex8_to_float(payload)
