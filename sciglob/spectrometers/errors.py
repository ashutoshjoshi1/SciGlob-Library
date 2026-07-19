"""Avantes AvaSpec DLL error table and lookup helpers.

The table is the complete, verbatim error list mined from the field-proven
Santana driver (spec section 3, ``ava1_spectrometer.py:48-90``), extended with
two host-side sentinels:

* ``-999`` -- local "spectrometer operation timed out" sentinel (**not** a DLL
  code) used by the wait/recovery layer.
* ``1000`` -- ``AVS_Activate`` failure return ("Invalid Handle"); the
  ``AVS_INVALID_HANDLE`` constant.

This module is pure Python and imports no DLL, so it is safe to import on any
platform.
"""

# AVS_Activate returns this value (not a negative error code) on failure.
# Field: avantes_ctypes.py:88-89, ava1_spectrometer.py:1177-1211.
AVS_INVALID_HANDLE: int = 1000

# Host-side timeout sentinel -- never returned by the DLL. Spec section 3.
AVS_TIMEOUT_SENTINEL: int = -999

# Complete verbatim error table -- spec section 3 (ava1_spectrometer.py:48-90).
# Reserved slots (-7, -13) are kept; -23 is intentionally absent (as in the
# field table); -999 and 1000 are the host-side sentinels described above.
ERROR_MESSAGES: dict[int, str] = {
    0: "OK",
    -1: "Function called with invalid parameter value.",
    -2: "Operation not supported, ie: Function called to use 16bit ADC mode, with 14bit ADC hardware.",
    -3: "Opening communication failed or time-out during communication occurred.",
    -4: "AvsHandle is unknown in the DLL.",
    -5: "Function is called while result of previous function is not received yet.",
    -6: "No answer received from device.",
    -7: "Reserved (-7)",
    -8: "No measurement data is received at the point AVS_GetScopeData is called (Invalid meas data).",
    -9: "Allocated buffer size to small.",
    -10: "Measurement preparation failed because pixel range is invalid.",
    -11: "Measurement preparation failed because integration time is invalid (for selected sensor).",
    -12: (
        "Measurement preparation failed because invalid combination of parameters, e.g. "
        "integration time of (600000) and (Navg >5000)."
    ),
    -13: "Reserved (-13)",
    -14: "Measurement preparation failed because no measurement buffers available.",
    -15: "Unknown error reason received from spectrometer.",
    -16: "Error in communication occurred.",
    -17: "No more spectra available in RAM, all read or measurement not started yet.",
    -18: "DLL version information can not be retrieved.",
    -19: "Memory allocation error in the DLL.",
    -20: "Function called before AVS_Init() is called.",
    -21: (
        "Function failed because AvaSpec is in wrong state (e.g AVS_StartMeasurement while "
        "measurement is pending)."
    ),
    -22: "Reply is not a recognized protocol message",
    -24: (
        "Error occurred while opening a bus device on the host. E.g. USB device access denied "
        "due to user rights"
    ),
    -25: "A read error has occurred when reading the onboard temperature sensor",
    -26: "A write error has occurred.",
    -27: "Library could not be initialized due to an Ethernet connection initialization error.",
    -28: (
        "The device-type information stored in the spectrometer isn't recognized as one of the "
        "known device types."
    ),
    -29: (
        "The AVS_GetDeviceType function is used, but the secure config (holding the device type "
        "information) hasn't been read yet. Most likely the device isn't initialised correctly."
    ),
    -30: "Unexpected response from spectrometer while getting measurement data",
    -100: "NrOfPixel in Device data incorrect.",
    -101: "Gain Setting Out of Range.",
    -102: "OffSet Setting Out of Range.",
    -120: "Use of AVS_SetSensitivityMode() not supported by detector type (dll v9.11+)",
    -121: "Use of AVS_SetSensitivityMode() not supported by firmware version",
    -122: "Use of AVS_SetSensitivityMode() not supported by FPGA version",
    -141: "Incorrect start pixel found in EEPROM",
    -142: "Incorrect end pixel found in EEPROM",
    -143: "Incorrect start or end pixel found in EEPROM",
    -144: "Factor should be in range 0.0 -4.0",
    -999: "Spectrometer operation timed out.",
    1000: "Invalid Handle.",
}


def get_error_message(code: int) -> str:
    """Return the verbatim message for an AvaSpec error code.

    Args:
        code: DLL return code (or one of the host-side sentinels).

    Returns:
        The exact message string for a known code, or
        ``"unknown error code (N)"`` for any code not in the table.
    """
    try:
        code = int(code)
    except (TypeError, ValueError):
        return f"unknown error code ({code!r})"
    if code in ERROR_MESSAGES:
        return ERROR_MESSAGES[code]
    return f"unknown error code ({code})"


def format_error(code: int) -> str:
    """Format a code the way the field driver's ``get_error`` did.

    ``0`` -> ``"OK"``; a known non-zero code -> ``"error code N, <message>"``;
    an unknown code -> ``"unknown error code (N)"`` (ava1_spectrometer.py:915-938).
    """
    code = int(code)
    if code == 0:
        return "OK"
    if code in ERROR_MESSAGES:
        return f"error code {code}, {ERROR_MESSAGES[code]}"
    return f"unknown error code ({code})"
