# Rivian long-tuning-tizi Branch Changes

This document describes the changes on the `long-tuning-tizi` branch (based on `sunnypilot/release-tizi`).

---

## 1. Enable Longitudinal Control Without Additional Harness

**Goal:** Allow openpilot longitudinal control on Rivian without the speed/gap button harness (which provides `Bus.alt` for wheel button signals).

### Files Modified

#### `opendbc_repo/opendbc/car/rivian/interface.py`

- In `_get_params`: Set `ret.alphaLongitudinalAvailable = True` (was `False`)
- In `_get_params_sp`:
  - Move `stock_cp.alphaLongitudinalAvailable = True` outside the harness fingerprint check (so it applies to all Rivians)
  - When `alpha_long` is enabled and harness is NOT detected, set `ret.flags |= RivianFlagsSP.LONGITUDINAL_WITHOUT_HARNESS`

#### `opendbc_repo/opendbc/sunnypilot/car/rivian/values.py`

- Add new flag: `LONGITUDINAL_WITHOUT_HARNESS = 2` to `RivianFlagsSP(IntFlag)`

#### `opendbc_repo/opendbc/sunnypilot/car/rivian/carstate_ext.py`

- Add `update_longitudinal_without_harness()` method
- In `update()`: add `elif` branch to call `update_longitudinal_without_harness` when `LONGITUDINAL_WITHOUT_HARNESS` flag is set

### Key Design Decisions

- `pcmCruise` stays `True` — Rivian's stock ACM manages cruise enable/disable state.
- Without the harness, only `Bus.pt` signals are available (no `Bus.alt` for wheel buttons).
- Speed control uses the stalk signal `VDM_UserAdasRequest` on `Bus.pt`.

---

## 2. Stalk Tap/Hold to Adjust Cruise Speed

**Goal:** When cruise is enabled, use the stalk (down direction) to increase set speed: tap = +1 mph, hold = snap to next 5 mph.

### File Modified

#### `opendbc_repo/opendbc/sunnypilot/car/rivian/carstate_ext.py`

### Behavior Summary

| Action | Condition | Result |
|--------|-----------|--------|
| Tap (release < 0.5s) | Normal | +1 mph |
| Tap (release < 0.5s) | Gas pressed AND current speed > set speed | Set cruise to current speed |
| Hold (every 0.5s) | — | Snap to next 5 mph (e.g., 47→50→55→60) |

### Key Details

- Control loop runs at 100Hz, so 50 frames = 0.5 second
- Tap is detected on **release** (counter resets to 0 while previous was > 0)
- Hold fires at every `counter % 50 == 0` (i.e., at 0.5s, 1s, 1.5s...)
- Hold snaps to next multiple of 5 mph rather than adding a flat 5
- Speed bounds: 20–85 mph (`MIN_SET_SPEED` / `MAX_SET_SPEED`)
- Stalk "down" = `VDM_UserAdasRequest` values 3 or 4
- Stalk "up" passes through to ACM to cancel cruise

---

## 3. UI Button to Cycle Driving Personality

**Goal:** Add an on-screen button that cycles through Aggressive/Standard/Relaxed driving personalities. Only visible when longitudinal control is enabled.

### Files Added

#### `selfdrive/ui/onroad/personality_button.py` (new file)

### Files Modified

#### `selfdrive/ui/onroad/hud_renderer.py`

### Visual Design

- **Position:** Middle of left side, vertically centered, x-offset 60px from content edge
- **Size:** 300×300 pixels
- **Appearance:** Circle ring outline with 3-letter label inside
  - AGR = red (`255, 75, 75`)
  - STD = white (`255, 255, 255`)
  - RLX = blue (`75, 200, 255`)
- **Interaction:** Tap cycles 0→1→2→0 (Aggressive→Standard→Relaxed→Aggressive)
- **Visibility:** Only shown when `ui_state.has_longitudinal_control` is True
- **Param:** Writes `LongitudinalPersonality` (int 0/1/2) on tap
- **Sync:** Reads personality from `selfdriveState` messages to stay in sync with external changes

---

## 4. Longitudinal Tuning Parameters

**Goal:** Improve longitudinal response and stopping behavior.

### File Modified

#### `opendbc_repo/opendbc/car/rivian/interface.py`

| Parameter | Before | After | Reason |
|-----------|--------|-------|--------|
| `longitudinalActuatorDelay` | 0.35 | 0.15 | See actuator delay analysis below |
| `stopAccel` | 0 | -0.2 | Light braking at stop for smoother hold |
| `jerk_factor` (aggressive) | 0.5 | 0.3 | Lower jerk penalty allows faster acceleration changes when catching up to lead |
| `longitudinalTuning.kpBP` | [0.] | [0., 35.] | Speed breakpoints for proportional gain (m/s) |
| `longitudinalTuning.kpV` | [0.] | [1.0, 0.3] | Proportional gain: strong from stop for faster catch-up, gentle at highway |
| `longitudinalTuning.kiBP` | [0.] | [0., 5., 35.] | Speed breakpoints for integral gain (m/s) |
| `longitudinalTuning.kiV` | [0.] | [1.2, 0.8, 0.5] | Integral gain: higher at low speed for stopping, lower at highway for smoothness (Honda-matched) |

### Jerk Factor Analysis

The MPC planner uses cost weights to balance smoothness vs responsiveness. The `jerk_factor`
multiplies two costs:
- `A_CHANGE_COST` (200): penalty for changing acceleration between timesteps
- `J_EGO_COST` (5): penalty for jerk (rate of acceleration change)

With `jerk_factor = 0.5` (stock aggressive): effective costs are 100 and 2.5
With `jerk_factor = 0.3` (new): effective costs are 60 and 1.5

**Problem observed (route 00000039--371bfe3efb, segment 7):**

When the lead car accelerated away from ~37 mph, the planner only commanded 0.6–0.8 m/s²
despite the car being capable of 1.2+ m/s². The gap took excessively long to close (~2s
following distance during catch-up vs 1.25s target). The planner was being too conservative
about ramping up acceleration.

**Why not change T_FOLLOW:** The steady-state following distance at 1.25s is acceptable.
The issue is purely the *transition speed* — how fast the planner ramps acceleration to
close the gap. Reducing jerk_factor allows faster ramp-up without changing the target gap.

**Why kpV/kiV didn't help:** Log data showed the car was *overdelivering* relative to
commands (actual > commanded). The PID was working correctly. The bottleneck was the planner
not asking for enough acceleration in the first place due to high jerk penalties.

### Actuator Delay Analysis

The Rivian has asymmetric actuator response — braking is nearly instant but acceleration from
standstill has significant delay. A single `longitudinalActuatorDelay` value is a compromise.

**Acceleration from standstill (route 00000035--1e784df48b, segment 5):**

| Time (s) | Commanded (m/s²) | Actual (m/s²) | Notes |
|----------|-----------------|---------------|-------|
| 16.0 | 0.34 | 0.0 | Command starts, no response |
| 16.4 | 0.80 | 0.0 | Still no response |
| 16.8 | 1.30 | 0.0 | ~800ms with zero response |
| 16.82 | 1.30 | 0.21 | Car finally starts moving |
| 16.91 | 0.53 | 1.66 | Overshoots, then settles |

**Measured acceleration delay from standstill: ~800ms**

**Braking at 27 mph (same route, segment 3):**

| Time (s) | Commanded (m/s²) | Actual (m/s²) | Notes |
|----------|-----------------|---------------|-------|
| 10.6 | -0.36 | -0.69 | Already braking harder than commanded |
| 10.7 | -0.57 | -0.52 | Tracking closely |
| 10.8 | -0.57 | -0.62 | <200ms delay |

**Measured braking delay: ~100-200ms**

**Decision:** Keep `longitudinalActuatorDelay = 0.15` to avoid braking too conservatively (which
creates excessive gap to lead car). Rely on kpV/kiV to compensate for the slow acceleration
response instead — the PID adds extra output when the car underdelivers on accel commands.

---

## 5. Mask Stalk Signal from ACM

**Goal:** Prevent the ACM from showing "driver assistance not available" when the stalk is tapped for speed adjustment while cruise is active.

### Files Modified

#### `opendbc_repo/opendbc/safety/modes/rivian.h`

- Added `{0x162, 2, 8, .check_relay = true}` to `RIVIAN_LONG_TX_MSGS`
- This allows openpilot to send `VDM_AdasSts` on Bus 2 and blocks the original forwarded message

#### `opendbc_repo/opendbc/car/rivian/riviancan.py`

- Added `user_adas_request` parameter to `create_adas_status()` for overriding the stalk signal

#### `opendbc_repo/opendbc/car/rivian/carcontroller.py`

- When longitudinal control is active, forwards `VDM_AdasSts` to ACM with selective masking:
  - **DOWN signals (3, 4):** Masked to IDLE (0) only when `cruiseState.enabled` is True
  - **UP signals (1, 2):** Always passed through so ACM can cancel cruise
  - **When cruise is not enabled:** All signals pass through so ACM can enable cruise

#### `panda/board/obj/panda_h7.bin.signed`

- Rebuilt panda firmware with the updated safety rules

### Behavior

| Cruise state | Stalk signal | What ACM sees | Result |
|---|---|---|---|
| Not enabled | DOWN (enable) | Passes through | ACM enables cruise |
| Enabled | DOWN (speed adj) | Masked to IDLE | No ACM error, openpilot adjusts speed |
| Enabled | UP (cancel) | Passes through | ACM cancels cruise |

---

## 6. Big Cruise Speed Display on Adjustment

**Goal:** Show the cruise set speed in a large font centered on screen when the speed is adjusted, for easy visibility.

### File Modified

#### `selfdrive/ui/onroad/hud_renderer.py`

### Behavior

- Only shown when `cruiseState.enabled` is True (cruise is actually active)
- When cruise speed changes (tap or hold), displays the set speed in the center of the screen
- Dark grey backdrop covers the full screen (same as "Reverse Gear" alert: `#151515` at 94% opacity)
- Font: bright white, 65% of screen height
- Disappears 3 seconds after the last speed change
- Updates in real time with each tap/hold (timer resets on every change)
- Immediately hidden when cruise is disabled
