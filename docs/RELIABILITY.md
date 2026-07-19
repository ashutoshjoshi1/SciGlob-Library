# Reliability Doctrine

This document captures the *why* behind sciglob's hardware-handling code. Every
rule here was paid for by a real field incident on a deployed Pandora-class
instrument. They are distilled from two field-proven codebases (the Blick suite
and the Pandora2.0 port) and encoded architecturally in this library so that a
future maintainer does not "simplify" a fix away without understanding what it
protects against.

> **Rule:** when this document and the source code disagree, the source wins —
> but if you are about to remove one of these behaviors, read the incident first.

---

## 1. Serial QA doctrine

Every question/answer exchange follows the same field-hardened cycle
(`SerialConnection.ask`):

1. **Drain stale input before every write.** A timed-out earlier read can leave
   a partial answer in the OS buffer. Reading it as the answer to the *next*
   question is a classic cross-talk bug. `ask()` drains (up to 10×5000 bytes,
   then flushes) before writing.
2. **Poll, don't block.** Ports are opened with `timeout=0` and read in an 8 ms
   poll loop. This keeps recovery threads responsive and lets a watchdog abort a
   stuck read.
3. **Grace seconds for short questions.** A question with a short timeout
   (≤ 4 s) that times out gets up to three extra 1-second waits before giving
   up. Field lesson (Blick `blick_serial.py:663`): *"changed from [1] to [27]
   because sometimes the answer is delayed."* Sensor answers straggle; a hard
   cutoff drops good data. Long actions (tracker reset, power cycle) get **no**
   grace — they either answer within their generous budget or they have failed.
4. **Re-ask on unexpected answers.** An answer that fails validation is re-asked
   after ~0.5 s, up to three times, before raising. Transient line noise does
   not become a hard failure.
5. **latin-1 everywhere.** All serial text is latin-1 with errors ignored, so a
   stray high byte never raises a `UnicodeDecodeError` mid-parse.
6. **Per-action timeouts, never a generic default.** The verified per-action
   timeout registry lives in `TIMING_CONFIG` (0.4 s identification probe, 2 s
   fast queries, 4 s sensor reads, 12 s device actions, 30 s tracker answers,
   8 s ESP32 answers). A one-size default masks real hangs.

## 2. Port-collision guard (unit 071)

Two device objects that silently share one COM port corrupt each other's answer
streams — the failure looks like random protocol errors and is maddening to
diagnose. `PortRegistry` is a process-wide claim table: opening a port already
owned by another device raises `PortCollisionError` naming **both** devices and
the port. The `Instrument` facade relies on this so an IMU and an SBHS
mis-assigned to the same port fail loudly at open, not subtly at runtime.

## 3. ESP32 sensor boxes (SBHS / ASB)

The ESP32-based JSON sensor boxes have a UART that is easy to wedge. The rules
below are non-negotiable and are all enforced in `SerialConnection(esp32_safe=True)`
plus the `SBHS`/`ASB` drivers:

1. **Open with `dsrdtr=False`, then explicitly assert DTR and RTS.** On Windows,
   opening with `dsrdtr=True` puts the driver in `DTR_CONTROL_HANDSHAKE` and
   silently ignores manual `ser.dtr` writes — pyserial never checks the
   `EscapeCommFunction` return value, so the failure is invisible. We open with
   handshake off and set the lines ourselves.
2. **Never pulse the reset lines during a normal open.** The ESP32 needs
   0.5–2 s after boot before its UART listens; a reset pulse at connect time
   creates an unanswerable race. `open()` asserts the lines and stops.
3. **`reset_pulse()` is an explicit recovery action only.** It drops DTR (EN
   low, IO0 high) for 0.5 s then re-asserts, booting the module into its
   application firmware. It is used only after a failed identify with an open
   handle, or on a third consecutive read failure, and automatic firings are
   throttled to ≥ 600 s apart.
4. **Allow ~8 s for an answer, and parse the last complete JSON record.** ESP32
   answers are slow and stale fragments from earlier timed-out reads can precede
   the real record. The driver keeps everything up to the final terminator and
   takes the last complete JSON object.
5. **Cache the sensor record ~10 s.** One `T`/`H`/`P` query returns the full
   sensor record; sibling quantities are served from cache instead of hammering
   the box with three round-trips.

### Identification without a configured ID (v0.0.8.11)

When no device ID is configured, identification must still succeed. The driver
matches the **hardware-type signature first** (`"Hardware":3` = SBHS,
`"Hardware":4` = ASB) and falls back to a configured-ID substring second. An
empty ID list must never make identification impossible. Finding an ASB where an
SBHS was expected (or vice-versa) is reported as **error code 98**, not accepted.

## 4. The Avantes reliability doctrine

The Avantes spectrometer is the hardest-won knowledge in the instrument. These
rules come from real outages (Pandora 288 Santee Sioux, unit 071 Columbia) and
are architectural, not incidental.

1. **One `AVS_Init` per process, one `AVS_Done` at exit.** A module-level session
   manager (`sciglob.spectrometers.session.AvaSession`) owns init/done/restart;
   device objects never call them. Init retries once via `AVS_Done` → `AVS_Init`
   on failure.
2. **A process-wide `RLock` around every `AVS_*` call.** All DLL calls route
   through one chokepoint (`AvaSession._avs`). Field lesson: *"AVS_StopMeasure()
   was moved ... because this function was giving problems when it is sent while
   receiving data from other spec."* On a dual-spectrometer unit, a call on one
   channel during the other's data transfer corrupts both. The lock serializes
   them.
3. **`AVS_Done` can hang forever.** Field lesson: *"This is a blocking call
   function! If the ... thread disappears, the software will keep blocked here
   forever! It is needed to implement a timeout."* `AvaSession.done()` runs it
   under an external watchdog timeout.
4. **Tier A recovery never calls `AVS_Done`/`AVS_Init`.** On a device drop:
   deactivate the stale handle → poll re-enumeration → settle → re-`AVS_Activate`
   with a **fresh identity each attempt**. The sibling spectrometer on a
   dual-spec unit must keep measuring throughout — so the shared session is never
   torn down in Tier A.
5. **Tier B is a coordinated session restart.** Only when Tier A exhausts with a
   persistent `AVS_Activate == 1000` does the driver raise
   `SessionRestartRequired`. The coordinator then quiesces *all* channels,
   `AVS_Done` → `AVS_Init`, and reactivates everyone. `IN_USE_BY_OTHER` (AvaSoft
   running) is excluded from this path — that is an operator problem, reported,
   not a wedge.
6. **Wedge cures are gated on "no data since last recovery."** A connect-time
   integration-time rejection, or an activate-but-mute link, triggers a single
   `AVS_ResetDevice` reboot — but **only on AS7010/AS7007** hardware, and a rapid
   re-fail reboots again only if *no data arrived since the last recovery*. Never
   reboot a glitchy-but-working link.
7. **Dead-handle guards everywhere.** `set_it`, `measure`, `read_aux_sensor`,
   `abort`, and `read_data` all no-op cleanly when the handle or `spec_id` is
   `None`. A freed handle reached through a native call is an uncatchable access
   violation, not a Python exception — so the guard must be *before* the call.
8. **External power-cycle coordination.** `mark_power_cycled()` clears `spec_id`
   (leaving the shared DLL handle intact) and **must** be invoked before any
   relay-driven USB power cycle — the head-sensor `S1s`/`S2s` relay or a Samirob
   channel. The `HeadSensor.spec_power_cycle()` method fires a registered hook
   that does exactly this before dropping USB power (the v0.0.8.7 crash class:
   a live handle whose USB vanished = access violation).
9. **No GUI assumptions.** All waits are plain `time.sleep` slices with an
   optional user-supplied `pump` callback. The library never imports wx/Qt;
   hosts that need event pumping pass a callable.

## 5. Graceful degradation

The `Instrument` facade never throws away the whole instrument because one sensor
is unplugged. Each device open is attempted independently; failures are collected
per-device and the device becomes simulated or `None` per the `strict` flag.
Field lesson from the Pandora2.0 port: *"The application keeps running with stubs
so the operator can fix one cable at a time without restarting the app."*
`Instrument.status()` reports each device as connected / simulated / error.

## 6. IMU "connected but silent" diagnosis (unit 071 / 999)

The xIMU3 is push-based and never polled. The driver keeps **per-message-type
counters** under a lock, in addition to the latest values. A device that is
connected but silent (counters not advancing) is a distinct, diagnosable state —
distinguishing "no cable" from "cable present, firmware mute" saved a field trip.
`IMU.is_streaming` is true only while the counters advance.
