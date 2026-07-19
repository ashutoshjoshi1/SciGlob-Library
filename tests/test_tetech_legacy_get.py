"""Regression: TETech1/2 GET parsing must strip the leading '*' control char.

Real TETech1/2 answers are framed "*<hex><checksum>^". A prior bug left the
leading '*' in place, so hex2dec("*00c4") raised ValueError on every real GET
(masked by a test that fed a fabricated '*'-less answer). See the adversarial
review finding for temperature_controller.py.
"""

from sciglob.core.simulation import SimulatedTransport
from sciglob.devices.temperature_controller import TemperatureController


def _tc_over(responder, ctype="TETech1"):
    transport = SimulatedTransport(responder=responder, port=f"SIM_{ctype}")
    tc = TemperatureController(controller_type=ctype, connection=transport)
    tc.connect()
    return tc


def test_tetech1_get_temperature_strips_leading_star():
    # Device answers a control-temp GET with a realistic '*'-framed frame:
    # 0x00C4 = 196 -> /10 = 19.6 degC. Trailing "a5" stands in for the checksum.
    def responder(data: bytes):
        text = data.decode("latin-1")
        if text.startswith("*0161"):  # T1 (control sensor temp) read
            return "*00c4a5^"
        return "*0060^"  # connection_test / anything else

    tc = _tc_over(responder, "TETech1")
    assert abs(tc.get_temperature() - 19.6) < 1e-6
    tc.disconnect()


def test_tetech2_get_setpoint_strips_leading_star():
    # TETech2 setpoint GET, factor 100: 0x09C4 = 2500 -> 25.0 degC.
    def responder(data: bytes):
        text = data.decode("latin-1")
        if text.startswith("*00500000000045"):  # ST read (TETech2)
            return "*000009c4XX^"
        return "*00430000000047^"

    tc = _tc_over(responder, "TETech2")
    # Just assert it parses to a finite number without raising ValueError.
    value = tc.get_setpoint()
    assert isinstance(value, float)
    tc.disconnect()
