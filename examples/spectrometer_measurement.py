"""Avantes spectrometer measurement example.

Runs against the simulator by default (no hardware, no DLL, no numpy required):

    python examples/spectrometer_measurement.py

To use a real AvaSpec spectrometer (pip install "sciglob[spectrometer]"):

    from sciglob.spectrometers import AvantesSpectrometer, get_session
    session = get_session()
    session.init()                      # one AVS_Init per process
    spec = AvantesSpectrometer(serial="1234", session=session)
    spec.connect()
    ...
    spec.disconnect()
    session.done()                      # one AVS_Done at exit

The session manager owns AVS_Init/AVS_Done and serializes every DLL call through
a process-wide lock; device objects never touch init/done. See docs/RELIABILITY.md.
"""

from sciglob.spectrometers import SimulatedSpectrometer


def main() -> None:
    spec = SimulatedSpectrometer(serial="SIM1234", npixels=2048)
    spec.connect()
    try:
        spec.set_integration_time(200.0)  # ms

        # Accumulate 10 cycles into one spectrum.
        spectrum = spec.measure(10)

        counts = spectrum.counts
        print(f"serial:            {spec.serial}")
        print(f"integration time:  {spec.integration_time_ms} ms")
        print(f"pixels:            {len(counts)}")
        print(f"max count:         {max(counts):.1f}")
        print(f"wavelength range:  {spec.wavelengths[0]:.1f} - {spec.wavelengths[-1]:.1f} nm")
        print(f"detector temp:     {spec.detector_temperature():.2f} degC")
        print(f"board temp:        {spec.board_temperature():.2f} degC")
    finally:
        spec.disconnect()


if __name__ == "__main__":
    main()
