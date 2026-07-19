"""Optional importer: build an ``Instrument`` config from a Pandora IOF file.

A Pandora *Instrument Operation File* (IOF) is a flat ``Key -> Value`` text
file describing one instrument's hardware. This module maps the relevant
serial-assignment and device-parameter lines onto the native ``Instrument``
config schema (see :mod:`sciglob.instrument`). The field mapping mirrors
NewBlick ``blick_io.py`` and Pandora2.0 ``serial_assignment_from_iof``.

Only the device configuration is consumed — processing/calibration blocks are
ignored. IOF "port number N" is a logical index; the Blick convention maps it
to ``COM{N}`` on Windows. That mapping is a **best-effort default** — verify or
override ``serial.port`` per device against the actual machine before opening
real hardware.

Usage::

    from sciglob import Instrument
    inst = Instrument.from_iof("Pandora999_OF.txt")
"""

import re
from typing import Any, Optional

_LINE = re.compile(r"^(?P<key>[^->]+?)\s*->\s*(?P<value>.*?)\s*$")


def parse_iof(filepath: str) -> dict[str, str]:
    """Parse an IOF file into an ordered ``{key: value}`` dict.

    Lines without the ``->`` separator (free-text annotations such as
    "This filter is tilted") are ignored. Later duplicate keys win.
    """
    out: dict[str, str] = {}
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for raw in f:
            m = _LINE.match(raw.rstrip("\n"))
            if m:
                out[m.group("key").strip()] = m.group("value").strip()
    return out


def _port_name(value: Optional[str]) -> Optional[str]:
    """Map an IOF logical 'port number' to a COM name (best-effort)."""
    if value is None:
        return None
    try:
        n = int(str(value).split()[0])
    except (ValueError, IndexError):
        return None
    return f"COM{n}"


def _floats(value: str) -> list[float]:
    out: list[float] = []
    for tok in value.split():
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


def _first_int(value: str) -> Optional[int]:
    for tok in value.split():
        try:
            return int(tok)
        except ValueError:
            continue
    return None


def config_from_iof(filepath: str) -> dict[str, Any]:
    """Build an ``Instrument`` config dict from an IOF file.

    Args:
        filepath: Path to the IOF text file.

    Returns:
        A config dict suitable for ``Instrument.from_dict`` /
        ``Instrument(config=...)``.
    """
    kv = parse_iof(filepath)
    config: dict[str, Any] = {}

    # ----- Head sensor + tracker + filter wheels -----
    if "Head sensor type" in kv:
        hs: dict[str, Any] = {
            "serial": {
                "port": _port_name(kv.get("Head sensor port number")),
                "baudrate": _first_int(kv.get("Head sensor-tracker connection baudrate", ""))
                or 9600,
            },
            "sensor_type": kv["Head sensor type"],
        }
        if "Tracker type" in kv:
            hs["tracker_type"] = kv["Tracker type"]
        res = _floats(kv.get("Tracker resolution [degrees per step]", ""))
        if res:
            hs["degrees_per_step"] = res[0]
        limits = _floats(kv.get("Tracker motion limits [deg]", ""))
        if len(limits) == 4:
            hs["motion_limits"] = limits
        home = _floats(kv.get("Tracker home position [deg]", ""))
        if len(home) == 2:
            hs["home_position"] = home

        fw1 = [kv.get(f"Filterwheel 1, position {i}") for i in range(1, 10)]
        fw2 = [kv.get(f"Filterwheel 2, position {i}") for i in range(1, 10)]
        if any(fw1):
            hs["fw1_filters"] = [f or "OPEN" for f in fw1]
        if any(fw2):
            hs["fw2_filters"] = [f or "OPEN" for f in fw2]

        config["head_sensor"] = hs

    # ----- Temperature controllers -----
    tcs: list[dict[str, Any]] = []
    # Single-controller IOF layout (as in the reference file).
    if "Temperature controller type" in kv:
        tcs.append(
            {
                "serial": {
                    "port": _port_name(kv.get("Temperature controller port number")),
                    "baudrate": _first_int(
                        kv.get("Temperature controller connection baudrate", "")
                    )
                    or 9600,
                },
                "controller_type": kv["Temperature controller type"],
            }
        )
    # Numbered layout (Temperature controller 1 type -> ...).
    for i in range(1, 5):
        tkey = f"Temperature controller {i} type"
        if tkey in kv:
            tcs.append(
                {
                    "serial": {
                        "port": _port_name(kv.get(f"Temperature controller {i} port number")),
                        "baudrate": _first_int(
                            kv.get(f"Temperature controller {i} connection baudrate", "")
                        )
                        or 9600,
                    },
                    "controller_type": kv[tkey],
                }
            )
    if tcs:
        config["temperature_controllers"] = tcs

    # ----- Spectrometer (Avantes / Ava1) -----
    readout = kv.get("Spectrometer read out type", "")
    if readout:
        sp: dict[str, Any] = {"readout_type": readout}
        if "Spectrometer unit ID" in kv:
            sp["serial_number"] = kv["Spectrometer unit ID"]
        npix = _first_int(kv.get("Number of pixels", ""))
        if npix:
            sp["npixels"] = npix
        nbits = _first_int(kv.get("A/D converter number of bits", ""))
        if nbits:
            sp["nbits"] = nbits
        disc = _floats(kv.get("Raw data discriminator factor", ""))
        if disc:
            sp["discriminator_factor"] = disc[0]
        min_it = _floats(kv.get("Minimum integration time [ms]", ""))
        if min_it:
            sp["min_it_ms"] = min_it[0]
        max_it = _floats(kv.get("Maximum integration time [ms]", ""))
        if max_it:
            sp["max_it_ms"] = max_it[0]
        itres = _floats(kv.get("Integration time resolution [ms]", ""))
        if itres:
            sp["it_resolution_ms"] = itres[0]
        config["spectrometer"] = sp

    # ----- Positioning / GPS -----
    for gps_key in ("Positioning system type", "GPS type"):
        if gps_key in kv:
            config["gps"] = {
                "serial": {
                    "port": _port_name(kv.get("Positioning system port number"))
                    or _port_name(kv.get("GPS port number")),
                },
                "system_type": kv[gps_key],
            }
            break

    # ----- SBHS / ASB / SRB (present in newer IOFs) -----
    for name, type_key, port_key, id_key in (
        ("sbhs", "SBHS type", "SBHS port number", "SBHS ID"),
        ("asb", "ASB type", "ASB port number", "ASB ID"),
        ("srb", "SRB type", "SRB port number", "SRB ID"),
    ):
        if type_key in kv or port_key in kv:
            section: dict[str, Any] = {"serial": {"port": _port_name(kv.get(port_key))}}
            if id_key in kv:
                section["device_id"] = kv[id_key]
            config[name] = section

    return config
