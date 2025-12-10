#!/usr/bin/env python3
"""
Basic usage examples for SciGlob Library.

This demonstrates connecting to and controlling:
- Head Sensor with integrated sensors
- Tracker (azimuth/zenith motors)
- Filter Wheels
- Temperature Controller
- Humidity Sensor
- GPS Positioning
"""

import logging

from sciglob import (
    GlobalSatGPS,
    HeadSensor,
    HumiditySensor,
    NovatelGPS,
    TemperatureController,
)


def head_sensor_example():
    """
    Example: Head Sensor with Tracker and Filter Wheels.

    The Head Sensor is the main hub that provides access to:
    - Tracker (motor control)
    - Filter Wheels (FW1, FW2)
    - Shadowband
    - Internal sensors (temp, humidity, pressure)
    """
    print("=" * 60)
    print("Head Sensor Example")
    print("=" * 60)

    # Configure filter wheel positions (customize for your setup)
    fw1_filters = [
        "OPEN", "U340", "BP300", "LPNIR", "ND1", "ND2", "ND3", "ND4", "OPAQUE"
    ]
    fw2_filters = [
        "OPEN", "DIFF", "U340+DIFF", "BP300+DIFF", "LPNIR+DIFF",
        "ND1", "ND2", "ND3", "OPAQUE"
    ]

    # Using context manager (recommended)
    with HeadSensor(
        port="/dev/ttyUSB0",  # Update for your system
        baudrate=9600,
        tracker_type="LuftBlickTR1",  # or "Directed Perceptions"
        degrees_per_step=0.01,
        motion_limits=[0, 90, 0, 360],  # [zen_min, zen_max, azi_min, azi_max]
        home_position=[0.0, 180.0],  # [zenith_home, azimuth_home]
        fw1_filters=fw1_filters,
        fw2_filters=fw2_filters,
    ) as hs:
        # Get device info
        print(f"Device ID: {hs.device_id}")
        print(f"Sensor Type: {hs.sensor_type}")
        print(f"Tracker Type: {hs.tracker_type}")

        # Read internal sensors (SciGlobHSN2 only)
        if hs.sensor_type == "SciGlobHSN2":
            sensors = hs.get_all_sensors()
            print(f"Temperature: {sensors.get('temperature', 'N/A')}°C")
            print(f"Humidity: {sensors.get('humidity', 'N/A')}%")
            print(f"Pressure: {sensors.get('pressure', 'N/A')} mbar")

        # --- Tracker Control ---
        print("\n--- Tracker Control ---")
        tracker = hs.tracker

        # Get current position
        zenith, azimuth = tracker.get_position()
        print(f"Current position: zenith={zenith}°, azimuth={azimuth}°")

        # Move to absolute position
        print("Moving to zenith=45°, azimuth=90°...")
        tracker.move_to(zenith=45.0, azimuth=90.0)

        # Move relative
        print("Moving relative: +10° zenith, +30° azimuth...")
        tracker.move_relative(delta_zenith=10.0, delta_azimuth=30.0)

        # Get updated position
        zenith, azimuth = tracker.get_position()
        print(f"New position: zenith={zenith}°, azimuth={azimuth}°")

        # Move to home
        print("Moving to home position...")
        tracker.home()

        # LuftBlickTR1 specific features
        if tracker.is_luftblick:
            temps = tracker.get_motor_temperatures()
            print(f"Motor temperatures: {temps}")

            alarms = tracker.get_motor_alarms()
            print(f"Motor alarms: {alarms}")

        # --- Filter Wheel Control ---
        print("\n--- Filter Wheel Control ---")
        fw1 = hs.filter_wheel_1

        # Show available filters
        print(f"FW1 filters: {fw1.get_available_filters()}")

        # Set by position
        fw1.set_position(1)
        print(f"FW1 at position {fw1.position}: {fw1.current_filter}")

        # Set by filter name
        fw1.set_filter("U340")
        print(f"FW1 now at: {fw1.current_filter}")

        # Reset to home
        fw1.reset()

        # --- Shadowband Control ---
        print("\n--- Shadowband Control ---")
        sb = hs.shadowband

        # Move by position (steps)
        sb.move_to_position(500)
        print(f"Shadowband at position {sb.position}, angle {sb.angle}°")

        # Move by angle
        sb.move_to_angle(30.0)

        # Reset
        sb.reset()

        # Get full status
        print("\n--- Full Status ---")
        status = hs.get_status()
        print(f"Status: {status}")


def temperature_controller_example():
    """
    Example: TETech Temperature Controller.
    """
    print("\n" + "=" * 60)
    print("Temperature Controller Example")
    print("=" * 60)

    with TemperatureController(
        port="/dev/ttyUSB1",  # Update for your system
        controller_type="TETech1",  # or "TETech2"
    ) as tc:
        # Read current temperature
        temp = tc.get_temperature()
        print(f"Current temperature: {temp}°C")

        # Read setpoint
        setpoint = tc.get_setpoint()
        print(f"Current setpoint: {setpoint}°C")

        # Set new temperature
        tc.set_temperature(25.0)
        print("Set temperature to 25.0°C")

        # Enable output
        tc.enable_output()
        print("Output enabled")

        # Get status
        status = tc.get_status()
        print(f"Status: {status}")


def humidity_sensor_example():
    """
    Example: HDC2080EVM Humidity Sensor.
    """
    print("\n" + "=" * 60)
    print("Humidity Sensor Example")
    print("=" * 60)

    with HumiditySensor(
        port="/dev/ttyUSB2",  # Update for your system
    ) as hs:
        # Read humidity
        humidity = hs.get_humidity()
        print(f"Humidity: {humidity}%")

        # Read temperature
        temp = hs.get_temperature()
        print(f"Temperature: {temp}°C")

        # Get both readings
        readings = hs.get_readings()
        print(f"Readings: {readings}")


def gps_example():
    """
    Example: GPS Positioning Systems.
    """
    print("\n" + "=" * 60)
    print("GPS Example")
    print("=" * 60)

    # GlobalSat GPS (simple)
    print("\n--- GlobalSat GPS ---")
    with GlobalSatGPS(port="/dev/ttyUSB3") as gps:
        position = gps.get_position()
        print(f"Position: {position}")

    # Novatel GPS + Gyroscope
    print("\n--- Novatel GPS ---")
    with NovatelGPS(port="/dev/ttyUSB4") as gps:
        position = gps.get_position()
        print(f"Position: {position}")

        orientation = gps.get_orientation()
        print(f"Orientation: {orientation}")


def manual_connection_example():
    """
    Example: Manual connection management (without context manager).
    """
    print("\n" + "=" * 60)
    print("Manual Connection Example")
    print("=" * 60)

    hs = HeadSensor(port="/dev/ttyUSB0")

    try:
        # Connect manually
        hs.connect()
        print(f"Connected: {hs.is_connected}")

        # Do operations
        print(f"Device: {hs.device_id}")

        # Access tracker
        tracker = hs.tracker
        tracker.home()

    finally:
        # Always disconnect
        hs.disconnect()
        print(f"Disconnected: {not hs.is_connected}")


if __name__ == "__main__":
    # Set up logging for debugging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Enable debug logging for sciglob
    # logging.getLogger("sciglob").setLevel(logging.DEBUG)

    print("SciGlob Library - Usage Examples")
    print("================================")
    print("\nNote: Update port names for your system!")
    print("      Linux: /dev/ttyUSB0, /dev/ttyACM0")
    print("      Windows: COM1, COM2, etc.")
    print()

    # Uncomment the examples you want to run:

    try:
        head_sensor_example()
    except Exception as e:
        print(f"Head sensor example failed: {e}")

    # try:
    #     temperature_controller_example()
    # except Exception as e:
    #     print(f"Temperature controller example failed: {e}")

    # try:
    #     humidity_sensor_example()
    # except Exception as e:
    #     print(f"Humidity sensor example failed: {e}")

    # try:
    #     gps_example()
    # except Exception as e:
    #     print(f"GPS example failed: {e}")

    # try:
    #     manual_connection_example()
    # except Exception as e:
    #     print(f"Manual connection example failed: {e}")
