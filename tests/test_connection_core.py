"""Core connection tests: port registry, ESP32 line discipline, QA loop, binary frames.

These cover the 0.2.0 core extensions (sciglob/core/connection.py and
sciglob/core/simulation.py), including the unit-071 port-collision regression.
"""

import pytest

from sciglob.core.connection import (
    PortRegistry,
    SerialConnection,
)
from sciglob.core.exceptions import (
    CommunicationError,
    PortCollisionError,
    TimeoutError,
)
from sciglob.core.simulation import SimulatedTransport, make_responder


@pytest.fixture(autouse=True)
def _clear_registry():
    """Each test starts with an empty process-wide port registry."""
    PortRegistry.clear()
    yield
    PortRegistry.clear()


# ---------------------------------------------------------------------------
# Port-collision guard (unit-071 field lesson)
# ---------------------------------------------------------------------------


def test_port_collision_refused():
    """Two device objects cannot own the same port in one process."""
    a = SimulatedTransport(port="COM7", owner="HeadSensor")
    a.open()

    b = SimulatedTransport(port="COM7", owner="SBHS")
    with pytest.raises(PortCollisionError) as excinfo:
        b.open()

    # The exception must name both devices and the port.
    err = excinfo.value
    assert err.port == "COM7"
    assert err.owning_device == "HeadSensor"
    assert err.requesting_device == "SBHS"
    assert "HeadSensor" in str(err) and "SBHS" in str(err)

    # After the owner releases, the port becomes claimable.
    a.close()
    b.open()
    assert b.is_open
    b.close()


def test_port_collision_case_insensitive_com():
    """COM port names are matched case-insensitively (com7 == COM7)."""
    a = SimulatedTransport(port="COM7", owner="A")
    a.open()
    b = SimulatedTransport(port="com7", owner="B")
    with pytest.raises(PortCollisionError):
        b.open()
    a.close()


def test_same_owner_reopen_allowed():
    """Re-claiming with the same owner name is not a collision."""
    PortRegistry.claim("COM3", "HeadSensor")
    PortRegistry.claim("COM3", "HeadSensor")  # no raise
    assert PortRegistry.owner_of("COM3") == "HeadSensor"
    PortRegistry.release("COM3", "HeadSensor")
    assert PortRegistry.owner_of("COM3") is None


# ---------------------------------------------------------------------------
# ESP32 line discipline
# ---------------------------------------------------------------------------


def test_esp32_open_asserts_both_lines_and_never_pulses_reset():
    """esp32_safe open asserts DTR+RTS and does NOT pulse the reset line."""
    t = SimulatedTransport(port="COM9", esp32_safe=True)
    t.open()
    # Both lines asserted high; no low->high pulse sequence during open.
    assert ("dtr", True) in [(e.line, e.value) for e in t.line_events]
    assert ("rts", True) in [(e.line, e.value) for e in t.line_events]
    # A reset pulse would drop DTR low; a normal open never does.
    assert ("dtr", False) not in [(e.line, e.value) for e in t.line_events]
    t.close()


def test_reset_pulse_line_sequence():
    """reset_pulse drops DTR low, holds, then re-asserts (EN low -> app boot)."""
    t = SimulatedTransport(port="COM9", esp32_safe=True)
    t.open()
    start = len(t.line_events)
    t.reset_pulse(hold=0.5)
    events = [(e.line, e.value) for e in t.line_events[start:]]
    # Sequence: RTS high (IO0 stays), DTR low (EN low), 0.5 s hold, DTR high.
    assert ("dtr", False) in events
    assert ("dtr", True) in events
    # The DTR-low must precede the DTR-high re-assert.
    dtr_low_idx = events.index(("dtr", False))
    dtr_high_idx = len(events) - 1 - events[::-1].index(("dtr", True))
    assert dtr_low_idx < dtr_high_idx
    # A 0.5 s hold was requested between them.
    holds = [e.value for e in t.line_events[start:] if e.line == "sleep"]
    assert 0.5 in holds
    t.close()


# ---------------------------------------------------------------------------
# QA loop: validation, grace retries, unexpected-answer escalation
# ---------------------------------------------------------------------------


def test_ask_returns_validated_answer():
    t = SimulatedTransport(responder=make_responder({"?": "SciGlobHSN2\n"}), port="Q1")
    t.open()
    assert t.ask("?", timeout=1.0) == "SciGlobHSN2"
    assert t.written == [b"?\r"]
    t.close()


def test_ask_returns_content_up_to_last_terminator():
    """ask() returns everything up to the final terminator (mirrors Blick
    check_answer polans). Isolating the last complete record from a multi-line
    answer is the device driver's job (see the SBHS last-record regression)."""
    t = SimulatedTransport(
        responder=make_responder({"v": b"stale-fragment\nGOOD\n"}), port="Q2"
    )
    t.open()
    answer = t.ask("v", timeout=1.0)
    # Both lines are present; the trailing terminator is stripped and the
    # device layer can split on "\n" to take the last complete record.
    assert answer.splitlines()[-1] == "GOOD"
    t.close()


def test_ask_unexpected_answer_escalates():
    """An answer failing the validator is re-asked, then raises after the budget."""
    t = SimulatedTransport(responder=make_responder({"x": "WRONG\n"}), port="Q3")
    t.open()
    with pytest.raises(CommunicationError):
        t.ask("x", timeout=1.0, validator=lambda a: a == "RIGHT", max_unexpected=3)
    # Re-asked max_unexpected times.
    assert t.written == [b"x\r", b"x\r", b"x\r"]
    t.close()


def test_ask_times_out_when_silent():
    t = SimulatedTransport(responder=make_responder({}, default=None), port="Q4")
    t.open()
    with pytest.raises(TimeoutError):
        # Short timeout so grace retries resolve fast in the test.
        t.ask("noreply", timeout=0.2, grace_retries=0)
    t.close()


# ---------------------------------------------------------------------------
# Binary frames
# ---------------------------------------------------------------------------


def test_write_frame_and_read_exact():
    """Binary frame round-trip for relay/Modbus-style protocols."""

    def responder(data: bytes):
        # Echo a fixed 4-byte answer frame.
        return bytes([0xA0, data[1], 0x01, (0xA0 + data[1] + 0x01) & 0xFF])

    t = SimulatedTransport(responder=responder, port="B1")
    t.open()
    t.write_frame(bytes([0xA0, 0x02, 0x05, (0xA0 + 0x02 + 0x05) & 0xFF]))
    answer = t.read_exact(4, timeout=1.0)
    assert len(answer) == 4
    assert answer[0] == 0xA0 and answer[1] == 0x02
    t.close()


def test_read_exact_times_out_on_short_frame():
    t = SimulatedTransport(responder=lambda d: b"\xa0", port="B2")
    t.open()
    t.write_frame(b"\x01")
    with pytest.raises(TimeoutError):
        t.read_exact(4, timeout=0.2)
    t.close()
