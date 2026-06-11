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
| Double tap (two taps within 0.5s) | TSR speed limit available and >= 35 mph | Set cruise to speed limit + 10% |
| Double tap (two taps within 0.5s) | TSR unavailable or < 35 mph | +1 mph (normal tap) |
| Hold (every 0.5s) | — | Snap to next 5 mph (e.g., 47→50→55→60) |

### Key Details

- Control loop runs at 100Hz, so 50 frames = 0.5 second
- Tap is detected on **release** (counter resets to 0 while previous was > 0)
- Double-tap detected when second tap release occurs within 50 frames of the first
- Hold fires at every `counter % 50 == 0` (i.e., at 0.5s, 1s, 1.5s...)
- Hold snaps to next multiple of 5 mph rather than adding a flat 5
- Speed limit from TSR (`ACM_tsrSpdDisClsMain`); must have received at least one valid reading
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
| `longitudinalActuatorDelay` | 0.35 | 0.15 | Faster response to accel commands |
| `stopAccel` | 0 | -0.2 | Light braking at stop for smoother hold |
| `longitudinalTuning.kiV` | (default) | [0.2] | Integral gain to reduce steady-state error |

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
