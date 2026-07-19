"""Device interfaces for SciGlob hardware."""

from sciglob.devices.asb import ASB, SimulatedASB, make_asb_responder
from sciglob.devices.filter_wheel import FilterWheel
from sciglob.devices.head_sensor import HeadSensor, SimulatedHeadSensor
from sciglob.devices.humidity_sensor import HumiditySensor
from sciglob.devices.positioning import GlobalSatGPS, NovatelGPS, PositioningSystem
from sciglob.devices.relay_board import RelayBoard, SimulatedRelayBoard, build_frame
from sciglob.devices.rs485_tracker import (
    AlarmStatus,
    AxisStatus,
    HomeResult,
    MoveResult,
    RS485Tracker,
    SimulatedRS485Tracker,
    modbus_crc16,
)
from sciglob.devices.sbhs import (
    SBHS,
    SensorEntry,
    SensorRecord,
    SimulatedSBHS,
    make_sbhs_responder,
)
from sciglob.devices.shadowband import Shadowband
from sciglob.devices.srb import SRB, SimulatedSRB
from sciglob.devices.temperature_controller import TemperatureController
from sciglob.devices.tracker import Tracker

__all__ = [
    # Head sensor + children
    "HeadSensor",
    "SimulatedHeadSensor",
    "Tracker",
    "FilterWheel",
    "Shadowband",
    # Temperature / humidity
    "TemperatureController",
    "HumiditySensor",
    # Positioning
    "PositioningSystem",
    "GlobalSatGPS",
    "NovatelGPS",
    # New serial sensor boxes
    "SRB",
    "SimulatedSRB",
    "SBHS",
    "SimulatedSBHS",
    "SensorRecord",
    "SensorEntry",
    "make_sbhs_responder",
    "ASB",
    "SimulatedASB",
    "make_asb_responder",
    # Relay board
    "RelayBoard",
    "SimulatedRelayBoard",
    "build_frame",
    # Direct-RS485 tracker
    "RS485Tracker",
    "SimulatedRS485Tracker",
    "AlarmStatus",
    "MoveResult",
    "HomeResult",
    "AxisStatus",
    "modbus_crc16",
]
