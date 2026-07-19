"""Tests for the Samirob 4-channel relay board (binary protocol)."""

import pytest

from sciglob.core.connection import PortRegistry
from sciglob.core.exceptions import DeviceIdentityError, RelayBoardError
from sciglob.core.simulation import SimulatedTransport
from sciglob.devices.relay_board import (
    Op,
    RelayBoard,
    RelayResponder,
    SimulatedRelayBoard,
    build_frame,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Ensure the process-wide port registry is clean around each test."""
    PortRegistry.clear()
    yield
    PortRegistry.clear()


def _cks(b0: int, b1: int, b2: int) -> int:
    return (b0 + b1 + b2) & 0xFF


# -- frame construction -------------------------------------------------


def test_build_frame_on_relay1_matches_spec_example():
    # spec section 2.3: Send [0xA0, 0x01, 0x03, 0xA4] to turn ON relay 1.
    assert build_frame(1, Op.ON_ACK) == bytes([0xA0, 0x01, 0x03, 0xA4])


def test_build_frame_checksum_is_sum_mod_256():
    frame = build_frame(4, Op.STATUS)
    assert frame[3] == _cks(0xA0, 0x04, 0x05)
    assert len(frame) == 4


# -- exact frames written for each operation ----------------------------


def test_on_writes_exact_frame_and_verifies_echo():
    board = SimulatedRelayBoard(port="SIM_ON")
    transport = board._connection
    assert isinstance(transport, SimulatedTransport)
    transport.written.clear()  # drop the connect() presence-probe frame

    board.on(1)

    assert transport.written == [bytes([0xA0, 0x01, 0x03, _cks(0xA0, 1, 0x03)])]
    assert board.state(1) is True
    board.disconnect()


def test_off_writes_exact_frame_and_verifies_echo():
    board = SimulatedRelayBoard(port="SIM_OFF", initial={2: True})
    transport = board._connection
    transport.written.clear()  # drop the connect() presence-probe frame

    board.off(2)

    assert transport.written == [bytes([0xA0, 0x02, 0x02, _cks(0xA0, 2, 0x02)])]
    assert board.state(2) is False
    board.disconnect()


def test_toggle_writes_exact_frame_and_returns_new_state():
    board = SimulatedRelayBoard(port="SIM_TOGGLE")
    transport = board._connection
    transport.written.clear()  # drop the connect() presence-probe frame

    new_state = board.toggle(3)

    assert transport.written == [bytes([0xA0, 0x03, 0x04, _cks(0xA0, 3, 0x04)])]
    assert new_state is True
    # Toggling again returns to OFF.
    assert board.toggle(3) is False
    board.disconnect()


def test_state_query_writes_exact_frame():
    board = SimulatedRelayBoard(port="SIM_QUERY")
    transport = board._connection
    transport.written.clear()  # drop the connect() presence-probe frame

    result = board.state(4)

    assert transport.written == [bytes([0xA0, 0x04, 0x05, _cks(0xA0, 4, 0x05)])]
    assert result is False
    board.disconnect()


def test_silent_on_off_use_opcodes_0x01_0x00_and_read_nothing():
    board = SimulatedRelayBoard(port="SIM_SILENT")
    transport = board._connection
    transport.written.clear()  # drop the connect() presence-probe frame

    board.on(1, silent=True)
    board.off(2, silent=True)

    assert transport.written == [
        bytes([0xA0, 0x01, 0x01, _cks(0xA0, 1, 0x01)]),
        bytes([0xA0, 0x02, 0x00, _cks(0xA0, 2, 0x00)]),
    ]
    board.disconnect()


# -- get_status and round-trip state -----------------------------------


def test_get_status_returns_all_channels():
    board = SimulatedRelayBoard(port="SIM_STATUS", initial={1: True, 3: True})

    status = board.get_status()

    assert status == {1: True, 2: False, 3: True, 4: False}
    board.disconnect()


def test_on_then_off_round_trip():
    board = SimulatedRelayBoard(port="SIM_RT")
    board.on(2)
    assert board.state(2) is True
    board.off(2)
    assert board.state(2) is False
    board.disconnect()


# -- checksum validation on read ----------------------------------------


def test_corrupted_echo_checksum_raises():
    def bad_responder(data: bytes) -> bytes:
        # Echo with a deliberately wrong checksum byte.
        return bytes([0xA0, data[1], 0x01, 0x00])

    transport = SimulatedTransport(responder=bad_responder, port="SIM_BADCKS")
    board = RelayBoard(port="SIM_BADCKS", connection=transport)
    board.connect(probe_on_connect=False)  # exercise the operational read path

    with pytest.raises(RelayBoardError, match="Checksum mismatch"):
        board.state(1)
    board.disconnect()


def test_bad_start_byte_raises():
    def bad_start(data: bytes) -> bytes:
        body = bytes([0x00, data[1], 0x01])
        return body + bytes([(sum(body)) & 0xFF])

    transport = SimulatedTransport(responder=bad_start, port="SIM_BADSTART")
    board = RelayBoard(port="SIM_BADSTART", connection=transport)
    board.connect(probe_on_connect=False)  # exercise the operational read path

    with pytest.raises(RelayBoardError, match="start byte"):
        board.state(1)
    board.disconnect()


def test_channel_mismatch_raises():
    def wrong_channel(data: bytes) -> bytes:
        body = bytes([0xA0, 0x02, 0x01])  # echoes channel 2 regardless
        return body + bytes([(sum(body)) & 0xFF])

    transport = SimulatedTransport(responder=wrong_channel, port="SIM_CHMIS")
    board = RelayBoard(port="SIM_CHMIS", connection=transport)
    board.connect()

    with pytest.raises(RelayBoardError, match="Channel mismatch"):
        board.state(1)
    board.disconnect()


def test_short_read_raises():
    def silent(data: bytes) -> None:
        return None  # board never answers a query -> short read / timeout

    transport = SimulatedTransport(responder=silent, port="SIM_SHORT")
    board = RelayBoard(port="SIM_SHORT", connection=transport, timeout=0.05)
    board.connect(probe_on_connect=False)  # exercise the operational read path

    with pytest.raises(RelayBoardError, match="too short"):
        board.state(1)
    board.disconnect()


def test_on_not_confirmed_raises_when_echo_reports_off():
    def always_off(data: bytes) -> bytes:
        body = bytes([0xA0, data[1], 0x00])  # always reports OFF
        return body + bytes([(sum(body)) & 0xFF])

    transport = SimulatedTransport(responder=always_off, port="SIM_NOTON")
    board = RelayBoard(port="SIM_NOTON", connection=transport)
    board.connect()

    with pytest.raises(RelayBoardError, match="not ON"):
        board.on(1)
    board.disconnect()


# -- channel validation -------------------------------------------------


@pytest.mark.parametrize("bad_channel", [0, 5, -1, 100])
def test_invalid_channel_raises(bad_channel):
    board = SimulatedRelayBoard(port="SIM_BADCH")
    with pytest.raises(RelayBoardError, match="between 1 and 4"):
        board.on(bad_channel)
    board.disconnect()


def test_non_integer_channel_raises():
    board = SimulatedRelayBoard(port="SIM_FLOATCH")
    with pytest.raises(RelayBoardError, match="integer"):
        board.state(2.5)  # type: ignore[arg-type]
    board.disconnect()


def test_operation_before_connect_raises():
    board = RelayBoard(port="COM_UNUSED")
    with pytest.raises(RelayBoardError, match="Not connected"):
        board.on(1)


# -- checksum both ways: written frames all carry a valid checksum ------


def test_written_frames_carry_valid_checksum():
    board = SimulatedRelayBoard(port="SIM_CKSWRITE")
    board.on(1)
    board.off(1)
    board.toggle(2)
    board.state(3)
    transport = board._connection
    for frame in transport.written:
        assert len(frame) == 4
        assert frame[3] == _cks(frame[0], frame[1], frame[2])
    board.disconnect()


# -- responder unit behavior -------------------------------------------


def test_responder_silent_opcodes_return_none():
    responder = RelayResponder(nrelays=4)
    assert responder(build_frame(1, Op.ON)) is None
    assert responder(build_frame(1, Op.OFF)) is None
    # But state was still updated.
    assert responder.state[1] is False  # ON then OFF


def test_responder_toggle_flips_state():
    responder = RelayResponder(nrelays=4)
    echo = responder(build_frame(2, Op.TOGGLE))
    assert echo is not None
    assert echo[2] == 0x01
    assert responder.state[2] is True


# -- connect() presence probe (spec section 6) -------------------------


def test_connect_probe_queries_channel_1_status():
    # The presence probe is a status query (0x05) on channel 1.
    board = SimulatedRelayBoard(port="SIM_PROBE", connect=False)
    transport = board._injected_connection
    assert isinstance(transport, SimulatedTransport)

    board.connect()

    assert transport.written[0] == bytes([0xA0, 0x01, 0x05, _cks(0xA0, 1, 0x05)])
    assert board.is_connected
    board.disconnect()


def test_connect_probe_raises_device_identity_error_on_no_echo():
    def silent(data: bytes) -> None:
        return None  # nothing answers the probe -> timeout / no echo

    transport = SimulatedTransport(responder=silent, port="SIM_NOECHO")
    board = RelayBoard(port="SIM_NOECHO", connection=transport, timeout=0.05)

    with pytest.raises(DeviceIdentityError):
        board.connect()
    # Failed probe must leave the board closed, not falsely "connected".
    assert not board.is_connected


def test_connect_probe_raises_device_identity_error_on_garbage_echo():
    def garbage(data: bytes) -> bytes:
        return bytes([0x00, 0xFF, 0xFF, 0xFF])  # bad start byte + bad checksum

    transport = SimulatedTransport(responder=garbage, port="SIM_GARBAGE")
    board = RelayBoard(port="SIM_GARBAGE", connection=transport, timeout=0.05)

    with pytest.raises(DeviceIdentityError):
        board.connect()
    assert not board.is_connected


def test_connect_probe_can_be_disabled():
    def silent(data: bytes) -> None:
        return None

    transport = SimulatedTransport(responder=silent, port="SIM_NOPROBE")
    board = RelayBoard(port="SIM_NOPROBE", connection=transport, timeout=0.05)

    board.connect(probe_on_connect=False)  # opens without probing
    assert board.is_connected
    assert transport.written == []  # no probe frame written
    board.disconnect()


def test_context_manager():
    with SimulatedRelayBoard(port="SIM_CTX", connect=False) as board:
        assert board.is_connected
        board.on(1)
    assert not board.is_connected
