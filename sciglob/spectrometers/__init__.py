"""Avantes AvaSpec spectrometer package for sciglob.

Public surface:

* :class:`AvantesSpectrometer` -- ctypes-over-DLL driver (never loads the DLL
  itself; all calls route through :class:`AvaSession`).
* :class:`SimulatedSpectrometer` -- hardware-free twin with the same surface.
* :class:`AvaSession` / :func:`get_session` -- the process-global DLL session
  and serialization chokepoint.
* :class:`Spectrum`, :class:`RecoveryPolicy` -- measurement result and recovery
  budgets/caps.
* ctypes structures, enums and the complete error table.

The whole package imports cleanly on machines with no DLL and no numpy.
"""

from sciglob.core.exceptions import SessionRestartRequired, SpectrometerError
from sciglob.spectrometers.avantes import (
    HAVE_NUMPY,
    AvantesSpectrometer,
    RecoveryPolicy,
    Spectrum,
    make_counts,
)
from sciglob.spectrometers.errors import (
    AVS_INVALID_HANDLE,
    AVS_TIMEOUT_SENTINEL,
    ERROR_MESSAGES,
    format_error,
    get_error_message,
)
from sciglob.spectrometers.session import (
    EXPECTED_DLL_VERSION,
    AvaSession,
    AvsIdentity,
    get_session,
    parse_dll_version,
    reset_global_session,
)
from sciglob.spectrometers.simulator import SimulatedSpectrometer
from sciglob.spectrometers.structures import (
    AVS_SERIAL_LEN,
    DEVICE_CONFIG_SIZE,
    DEVTYPE_NAMES,
    USER_ID_LEN,
    AvaDeviceType,
    AvsIdentityType,
    BroadcastAnswerType,
    DeviceConfigType,
    DeviceStatus,
    DstrStatusType,
    EthConnStatus,
    MeasConfigType,
    devtype_name,
)

__all__ = [
    # driver + twin
    "AvantesSpectrometer",
    "SimulatedSpectrometer",
    # session
    "AvaSession",
    "AvsIdentity",
    "get_session",
    "reset_global_session",
    "parse_dll_version",
    "EXPECTED_DLL_VERSION",
    # results / policy
    "Spectrum",
    "RecoveryPolicy",
    "make_counts",
    "HAVE_NUMPY",
    # errors
    "ERROR_MESSAGES",
    "get_error_message",
    "format_error",
    "AVS_INVALID_HANDLE",
    "AVS_TIMEOUT_SENTINEL",
    # structures / enums
    "AvsIdentityType",
    "BroadcastAnswerType",
    "MeasConfigType",
    "DeviceConfigType",
    "DstrStatusType",
    "AvaDeviceType",
    "EthConnStatus",
    "DeviceStatus",
    "DEVTYPE_NAMES",
    "devtype_name",
    "AVS_SERIAL_LEN",
    "USER_ID_LEN",
    "DEVICE_CONFIG_SIZE",
    # exceptions (re-export for convenience)
    "SpectrometerError",
    "SessionRestartRequired",
]
