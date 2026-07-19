"""Byte-exact ctypes structures for the Avantes AvaSpec DLL.

Pure ctypes -- this module loads no DLL and is importable on any platform.

The layouts follow the authoritative Santana driver (spec section 2,
``ava1_spectrometer.py:100-216``), which uses ``_pack_ = 1`` and **flattened**
nested fields, with the explicit warning "nesting of types does NOT work!!"
(ava1_spectrometer.py:123). The legacy BlickO / Pandora ports used nested
default-aligned sub-structs; for these field types the two layouts happen to
produce the same 41-byte payload, but the flattened packed layout is the
deliberate, authoritative one and is what we reproduce here.
"""

import ctypes
from ctypes import (
    c_char,
    c_float,
    c_uint8,
    c_uint16,
    c_uint32,
)
from enum import IntEnum

# Spec section 2: ava1_spectrometer.py:33-34.
AVS_SERIAL_LEN: int = 10
USER_ID_LEN: int = 64

# Size of the DeviceConfigType EEPROM blob -- spec section 2.4
# (AVS_GetParameter reqsize, ava1_spectrometer.py:1311-1317).
DEVICE_CONFIG_SIZE: int = 63484


class AvsIdentityType(ctypes.Structure):
    """USB device identity -- spec section 2.1 (ava1_spectrometer.py:100-104).

    75 bytes total. The ``Status`` byte is captured but never decoded in any
    field source (see :class:`DeviceStatus`).
    """

    _pack_ = 1
    _fields_ = [
        ("SerialNumber", c_char * AVS_SERIAL_LEN),
        ("UserFriendlyName", c_char * USER_ID_LEN),
        ("Status", c_char),
    ]


class BroadcastAnswerType(ctypes.Structure):
    """Ethernet-discovery answer -- spec section 2.2 (ava1_spectrometer.py:106-114)."""

    _pack_ = 1
    _fields_ = [
        ("InterfaceType", c_uint8),
        ("serial", c_char * AVS_SERIAL_LEN),
        ("port", c_uint16),
        ("status", c_uint8),
        ("RemoteHostIp", c_uint32),
        ("LocalIp", c_uint32),
        ("reserved", c_uint8 * 4),
    ]


class MeasConfigType(ctypes.Structure):
    """Measurement configuration -- spec section 2.3 (ava1_spectrometer.py:116-135).

    Flattened + ``_pack_ = 1``; 41-byte payload. ``m_IntegrationTime`` is a
    single-precision float in ms ("there might be a loss of precision").
    """

    _pack_ = 1
    _fields_ = [
        ("m_StartPixel", c_uint16),
        ("m_StopPixel", c_uint16),
        ("m_IntegrationTime", c_float),  # ms, single precision
        ("m_IntegrationDelay", c_uint32),  # FPGA clock cycles
        ("m_NrAverages", c_uint32),
        ("m_CorDynDark_m_Enable", c_uint8),
        ("m_CorDynDark_m_ForgetPercentage", c_uint8),
        ("m_Smoothing_m_SmoothPix", c_uint16),
        ("m_Smoothing_m_SmoothModel", c_uint8),
        ("m_SaturationDetection", c_uint8),
        ("m_Trigger_m_Mode", c_uint8),
        ("m_Trigger_m_Source", c_uint8),
        ("m_Trigger_m_SourceType", c_uint8),
        ("m_Control_m_StrobeControl", c_uint16),
        ("m_Control_m_LaserDelay", c_uint32),
        ("m_Control_m_LaserWidth", c_uint32),
        ("m_Control_m_LaserWaveLength", c_float),
        ("m_Control_m_StoreToRam", c_uint16),
    ]


# Bytes consumed by the leading DeviceConfigType fields we model explicitly.
# 2 + 2 + 64 + 1 + 2 + (5*4) = 91 bytes; the remainder is an opaque reserved
# tail so that ``sizeof`` matches the real 63484-byte EEPROM blob and the buffer
# passed to AVS_GetParameter is the size the DLL expects.
_DEVCFG_HEAD_BYTES = 2 + 2 + USER_ID_LEN + 1 + 2 + (5 * 4)


class DeviceConfigType(ctypes.Structure):
    """Device / EEPROM configuration -- spec section 2.4 (ava1_spectrometer.py:137-206).

    Only the leading fields the driver needs are modelled explicitly
    (``m_Detector_m_NrPixels`` and the wavelength-calibration polynomial
    ``m_Detector_m_aFit``); everything after ``m_aFit`` is folded into
    ``_reserved`` so the total size equals the real 63484-byte blob. Because
    the struct is ``_pack_ = 1``, the offsets of the modelled fields are exact.
    """

    _pack_ = 1
    _fields_ = [
        ("m_Len", c_uint16),
        ("m_ConfigVersion", c_uint16),
        ("m_aUserFriendlyId", c_char * USER_ID_LEN),
        ("m_Detector_m_SensorType", c_uint8),
        ("m_Detector_m_NrPixels", c_uint16),
        ("m_Detector_m_aFit", c_float * 5),  # wavelength-calibration polynomial
        ("_reserved", c_uint8 * (DEVICE_CONFIG_SIZE - _DEVCFG_HEAD_BYTES)),
    ]


class DstrStatusType(ctypes.Structure):
    """StoreToRam status -- spec section 2.5 (ava1_spectrometer.py:208-216)."""

    _pack_ = 1
    _fields_ = [
        ("m_TotalScans", c_uint32),
        ("m_UsedScans", c_uint32),
        ("m_Flags", c_uint32),
        ("m_IsStopEvent", c_uint8),
        ("m_IsOverflowEvent", c_uint8),
        ("m_IsInternalErrorEvent", c_uint8),
        ("m_Reserved", c_uint8),
    ]


class AvaDeviceType(IntEnum):
    """Spectrometer hardware family -- spec section 2.6 (ava1_spectrometer.py:36-40).

    Returned by ``AVS_GetDeviceType``. AS7010/AS7007 (and AS-MINI) are the only
    families that support ``AVS_ResetDevice`` (wedge cure); see recovery layer.
    """

    TYPE_UNKNOWN = 0
    TYPE_AS5216 = 1
    TYPE_ASMINI = 2
    TYPE_AS7010 = 3
    TYPE_AS7007 = 4


DEVTYPE_NAMES: dict[int, str] = {
    0: "TYPE_UNKNOWN",
    1: "TYPE_AS5216",
    2: "TYPE_ASMINI",
    3: "TYPE_AS7010",
    4: "TYPE_AS7007",
}


class EthConnStatus(IntEnum):
    """Ethernet connection status -- spec section 2.6 (ava1_spectrometer.py:42-46).

    Non-USB only; delivered via the connection-status callback.
    """

    ETH_CONN_STATUS_CONNECTING = 0
    ETH_CONN_STATUS_CONNECTED = 1
    ETH_CONN_STATUS_CONNECTED_NOMON = 2
    ETH_CONN_STATUS_NOCONNECTION = 3


DEV_STATUS_NAMES: dict[int, str] = {
    0: "ETH_CONN_STATUS_CONNECTING",
    1: "ETH_CONN_STATUS_CONNECTED",
    2: "ETH_CONN_STATUS_CONNECTED_NOMON",
    3: "ETH_CONN_STATUS_NOCONNECTION",
}


class DeviceStatus(IntEnum):
    """Meaning of the ``AvsIdentityType.Status`` byte.

    DOCTRINE ONLY (prompt.md:172, spec section 14): the ``USB_IN_USE_BY_OTHER``
    status is defined by the AvaSpec DLL headers but is **never decoded** in any
    mined field source. Provided so callers can interpret the captured Status
    byte; treat as advisory, not field-proven.
    """

    UNKNOWN = 0
    USB_AVAILABLE = 1
    USB_IN_USE_BY_APPLICATION = 2
    USB_IN_USE_BY_OTHER = 3
    ETH_AVAILABLE = 4
    ETH_IN_USE_BY_APPLICATION = 5
    ETH_IN_USE_BY_OTHER = 6
    ETH_ALREADY_IN_USE_USB = 7


def devtype_name(value: int) -> str:
    """Return the ``TYPE_*`` name for a device-type code (fallback for unknown)."""
    return DEVTYPE_NAMES.get(int(value), f"TYPE_UNKNOWN({value})")
