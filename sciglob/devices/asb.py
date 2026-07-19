"""ASB ESP32 JSON sensor box (SciGlob Air Sensors Box, Hardware type 4).

The ASB is the dual-BME280 + MPRLS variant of the ESP32/JSON sensor family. It
reuses the shared record-parsing, read-loop, caching and reset-pulse machinery
from :mod:`sciglob.devices.sbhs` (importing from ``sbhs.py`` is intentional --
that is the shared base module, not a forbidden shared file) and adds the
ASB-only ``AP`` (ambient pressure via MPRLS) reading.

Differences from SBHS (spec §3.2):
    * ``"Hardware":4`` instead of 3;
    * the ``Sensors`` array adds an ``{"ID":"MPRLS","Pressure":..}`` entry.

Example:
    >>> from sciglob.devices.asb import SimulatedASB
    >>> asb = SimulatedASB()
    >>> asb.connect()
    >>> round(asb.get_ambient_pressure(), 1)
    1008.7
    >>> asb.disconnect()
"""

import json
from typing import Any, Optional

from sciglob.core.connection import SerialConnection
from sciglob.core.exceptions import SensorError
from sciglob.core.protocols import ESP32_SENSOR_ERROR_MESSAGES, TIMING_CONFIG, SerialConfig
from sciglob.core.simulation import SimulatedTransport, make_responder
from sciglob.devices.sbhs import (
    ANSWER_END,
    ERR_PRESSURE_PARSE,
    QUESTION_END_CHAR,
    ESP32JsonSensor,
)


class ASB(ESP32JsonSensor):
    """SciGlob Air Sensors Box (ESP32/JSON, Hardware type 4, dual BME280 + MPRLS).

    Adds :meth:`get_ambient_pressure` (the MPRLS reading) on top of the shared
    temperature/humidity/pressure BME280 readings.
    """

    HARDWARE_TYPE = 4

    _device_name = "ASB"
    _device_description = "SciGlob Air Sensors Box (ESP32 JSON, Hardware type 4, dual BME280 + MPRLS)"
    _supported_types = ["ASB"]
    _command_reference = {
        "v": "Identify (returns JSON incl. 'Hardware' field)",
        "T": "Temperature (returns full JSON record)",
        "H": "Humidity (returns full JSON record)",
        "P": "Pressure (returns full JSON record)",
        "AP": "Ambient pressure via MPRLS (ASB only)",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        device_id: Optional[str] = None,
        timeout: float = TIMING_CONFIG["esp32_answer_timeout"],
        cache_ttl: float = TIMING_CONFIG["esp32_record_cache"],
        name: str = "ASB",
        config: Optional[Any] = None,
        serial_config: Optional[SerialConfig] = None,
        connection: Optional[SerialConnection] = None,
    ):
        super().__init__(
            port=port,
            baudrate=baudrate,
            device_id=device_id,
            timeout=timeout,
            cache_ttl=cache_ttl,
            name=name,
            config=config,
            serial_config=serial_config,
            connection=connection,
        )

    def get_ambient_pressure(self) -> float:
        """Ambient pressure in hPa from the MPRLS entry of the record (spec §3).

        The MPRLS pressure ships in the same JSON record as the BME280
        quantities, so it is served from the shared ~10 s cache.

        Raises:
            SensorError: no MPRLS entry, or its Pressure field is unparseable
                (error code 5).
        """
        entry = self.get_record().sensor("MPRLS")
        if entry is None or entry.pressure is None:
            raise SensorError(
                f"{ESP32_SENSOR_ERROR_MESSAGES[ERR_PRESSURE_PARSE]} (MPRLS) on {self.port}",
                error_code=ERR_PRESSURE_PARSE,
            )
        return entry.pressure


# -- simulation helpers -------------------------------------------------


def make_asb_responder(
    temperature: float = 21.0,
    humidity: float = 38.0,
    pressure: float = 1009.0,
    ambient_pressure: float = 1008.7,
    firmware: int = 4,
    uuid: str = "ASB-SIM-0001",
    hardware: int = 4,
) -> Any:
    """Build a responder emitting a realistic ASB JSON record for v/T/H/P/AP.

    The record adds an ``MPRLS`` entry to the ``Sensors`` array (spec §3.2).
    """
    record = {
        "Hardware": hardware,
        "Firmware": firmware,
        "UUID": uuid,
        "Sensors": [
            {
                "ID": "BME280",
                "Temperature": temperature,
                "Humidity": humidity,
                "Pressure": pressure,
            },
            {"ID": "MPRLS", "Pressure": ambient_pressure},
        ],
    }
    line = json.dumps(record) + ANSWER_END
    mapping: dict[str, Any] = {"v": line, "T": line, "H": line, "P": line, "AP": line}
    return make_responder(mapping, end_char=QUESTION_END_CHAR)


def SimulatedASB(
    port: str = "SIM_ASB",
    device_id: Optional[str] = None,
    temperature: float = 21.0,
    humidity: float = 38.0,
    pressure: float = 1009.0,
    ambient_pressure: float = 1008.7,
    firmware: int = 4,
    uuid: str = "ASB-SIM-0001",
    time_scale: float = 0.0,
) -> ASB:
    """Return an :class:`ASB` wired to a scripted :class:`SimulatedTransport`.

    The returned device is not yet connected; call ``connect()``.
    """
    transport = SimulatedTransport(
        responder=make_asb_responder(
            temperature=temperature,
            humidity=humidity,
            pressure=pressure,
            ambient_pressure=ambient_pressure,
            firmware=firmware,
            uuid=uuid,
        ),
        port=port,
        owner="ASB",
        esp32_safe=True,
        time_scale=time_scale,
    )
    return ASB(port=port, device_id=device_id, connection=transport)
