"""Full-instrument example — drive every subsystem through the Instrument facade.

Run entirely in software (no hardware needed):

    python examples/full_instrument.py

To talk to real hardware, write a YAML config (see below) and load it with
``Instrument.from_yaml("my_instrument.yaml")`` — drop the ``simulated=True``.

Example YAML::

    head_sensor:
      serial: {port: COM3, baudrate: 9600}
      sensor_type: SciGlobHSN2
      tracker_type: LuftBlickTR1
    temperature_controllers:
      - {serial: {port: COM4}, controller_type: TETech1090}
    sbhs: {serial: {port: COM8}}
    asb:  {serial: {port: COM9}}
    srb:  {serial: {port: COM11}}
    relay_board: {serial: {port: COM12}, nrelays: 4}
    spectrometer: {serial_number: "1234", npixels: 2048}
    camera: {backend: opencv, index: 0}
    imu: {serial: {port: COM13}}
    gps: {serial: {port: COM6}, system_type: GlobalSat}
"""

import logging

from sciglob import Instrument

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")


CONFIG = {
    "head_sensor": {"sensor_type": "SciGlobHSN2", "tracker_type": "LuftBlickTR1"},
    "temperature_controllers": [{"controller_type": "TETech1090"}],
    "sbhs": {},
    "asb": {},
    "srb": {},
    "relay_board": {"nrelays": 4},
    "spectrometer": {"serial_number": "SIM1234", "npixels": 2048},
    "camera": {},
    "imu": {},
}


def main() -> None:
    # simulated=True builds every device's simulation twin — no hardware needed.
    inst = Instrument(config=CONFIG, simulated=True)

    with inst:
        print("\n=== Per-device status ===")
        for name, st in inst.status().items():
            print(f"  {name:24s} {st['state']}")

        print("\n=== Tracker ===")
        inst.tracker.move_to(zenith=45.0, azimuth=180.0)
        print("  position:", inst.tracker.get_position())

        print("\n=== Filter wheel ===")
        inst.filter_wheel_1.set_filter("OPEN")
        print("  filter:", inst.filter_wheel_1.current_filter)

        print("\n=== ESP32 / SRB sensors ===")
        print("  SBHS humidity:", round(inst.sbhs.get_humidity(), 2), "%")
        print("  ASB ambient pressure:", round(inst.asb.get_ambient_pressure(), 2), "hPa")
        print("  SRB temperature:", round(inst.srb.get_temperature(), 2), "degC")

        print("\n=== Spectrometer ===")
        inst.spectrometer.set_integration_time(100)  # ms
        spectrum = inst.spectrometer.measure(5)
        print("  pixels:", len(spectrum.counts))
        print("  board temperature:", round(inst.spectrometer.board_temperature(), 2), "degC")

        print("\n=== Relay board ===")
        inst.relay_board.on(1)
        print("  relay 1 state:", inst.relay_board.state(1))
        inst.relay_board.off(1)

        print("\n=== Coordinated spectrometer power-cycle ===")
        # spec_power_cycle marks the spectrometer power-cycled BEFORE the relay
        # drops USB power (prevents the freed-handle crash class).
        inst.head_sensor.spec_power_cycle(1)
        print("  spectrometer connected after power-cycle:",
              inst.spectrometer.is_connected)

    print("\nInstrument closed cleanly.")


if __name__ == "__main__":
    main()
