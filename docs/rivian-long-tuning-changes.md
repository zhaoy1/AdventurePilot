# Rivian Longitudinal Tuning Branch Changes

This document describes the three major features implemented on the `long-tuning` branch for porting to other branches.

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

- Add `update_longitudinal_without_harness()` method (see Feature 2 below for details)
- In `update()`: add `elif` branch to call `update_longitudinal_without_harness` when `LONGITUDINAL_WITHOUT_HARNESS` flag is set

### Key Design Decisions

- `pcmCruise` stays `True` — Rivian's stock ACM manages cruise enable/disable state. Openpilot doesn't emit `accelCruise`/`decelCruise` button events needed for `buttonEnable` with `pcmCruise=False`.
- Without the harness, only `Bus.pt` signals are available (no `Bus.alt` for wheel buttons).
- Speed control uses the stalk signal `VDM_UserAdasRequest` on `Bus.pt`.

---

## 2. Stalk Tap/Hold to Adjust Cruise Speed

**Goal:** When cruise is enabled, use the stalk (down direction) to increase set speed: tap = +1 mph, hold = +5 mph per second.

### File Modified

#### `opendbc_repo/opendbc/sunnypilot/car/rivian/carstate_ext.py`

The `update_longitudinal_without_harness()` method implements:

```python
def update_longitudinal_without_harness(self, ret, can_parsers):
    cp = can_parsers[Bus.pt]

    if self.CP.openpilotLongitudinalControl:
      if not ret.cruiseState.enabled:
        self.set_speed = ret.vEgoCluster
      else:
        # VDM_UserAdasRequest: 0=IDLE, 1=UP_1, 2=UP_2, 3=DOWN_1, 4=DOWN_2
        stalk_down = int(cp.vl["VDM_AdasSts"]["VDM_UserAdasRequest"]) in (3, 4)
        prev_stalk_down_counter = self.stalk_down_counter
        self.stalk_down_counter = self.stalk_down_counter + 1 if stalk_down else 0

        tap_increment = 1.0 * CV.MPH_TO_MS
        hold_increment = 5.0 * CV.MPH_TO_MS

        if self.stalk_down_counter == 0 and prev_stalk_down_counter > 0:
          # Released: short press (< 1s) applies tap increment
          if prev_stalk_down_counter < 100:
            if ret.gasPressed and ret.vEgoCluster > self.set_speed:
              self.set_speed = ret.vEgoCluster
            else:
              self.set_speed += tap_increment
        elif self.stalk_down_counter > 0 and self.stalk_down_counter % 100 == 0:
          # Held for 1s (or multiples): apply hold increment
          self.set_speed += hold_increment

      self.set_speed = max(MIN_SET_SPEED, min(self.set_speed, MAX_SET_SPEED))
      ret.cruiseState.speed = self.set_speed
```

### Behavior Summary

| Action | Condition | Result |
|--------|-----------|--------|
| Tap (release < 1s) | Normal | +1 mph |
| Tap (release < 1s) | Gas pressed AND current speed > set speed | Set cruise to current speed |
| Hold (every 1s) | — | +5 mph |

### Key Details

- Control loop runs at 100Hz, so 100 frames = 1 second
- Tap is detected on **release** (counter resets to 0 while previous was > 0)
- Hold fires at every `counter % 100 == 0` (i.e., at 1s, 2s, 3s...)
- Speed bounds: 20–85 mph (`MIN_SET_SPEED` / `MAX_SET_SPEED`)
- Stalk "down" = `VDM_UserAdasRequest` values 3 or 4
- No decrease (stalk up) logic implemented currently

---

## 3. UI Button to Cycle Driving Personality

**Goal:** Add an on-screen button that cycles through Aggressive/Standard/Relaxed driving personalities. Only visible when longitudinal control is enabled.

### Files Added

#### `selfdrive/ui/onroad/personality_button.py` (new file)

```python
import pyray as rl
from cereal import log
from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

PERSONALITY_LABELS = {0: "AGR", 1: "STD", 2: "RLX"}
PERSONALITY_COLORS = {
  0: rl.Color(255, 75, 75, 255),
  1: rl.Color(255, 255, 255, 255),
  2: rl.Color(75, 200, 255, 255),
}


class PersonalityButton(Widget):
  def __init__(self, button_size: int):
    super().__init__()
    self._params = Params()
    self._personality: int = self._params.get("LongitudinalPersonality", return_default=True)
    self._rect = rl.Rectangle(0, 0, button_size, button_size)
    self._font = gui_app.font(FontWeight.BOLD)
    self._font_size = 72

  def set_rect(self, rect: rl.Rectangle) -> None:
    self._rect.x, self._rect.y = rect.x, rect.y

  def _update_state(self) -> None:
    if ui_state.sm.updated["selfdriveState"]:
      self._personality = log.LongitudinalPersonality.schema.enumerants[
        ui_state.sm["selfdriveState"].personality
      ]

  def _handle_mouse_release(self, _):
    super()._handle_mouse_release(_)
    self._personality = (self._personality + 1) % 3
    self._params.put("LongitudinalPersonality", self._personality)

  def _render(self, rect: rl.Rectangle) -> None:
    center_x = int(self._rect.x + self._rect.width // 2)
    center_y = int(self._rect.y + self._rect.height // 2)

    label = PERSONALITY_LABELS.get(self._personality, "STD")
    color = PERSONALITY_COLORS.get(self._personality, rl.WHITE)
    if self.is_pressed:
      color = rl.Color(color.r, color.g, color.b, 180)

    circle_radius = self._rect.width / 2 - 10
    rl.draw_ring(rl.Vector2(center_x, center_y), circle_radius - 3, circle_radius, 0, 360, 36, color)

    text_size = measure_text_cached(self._font, label, self._font_size)
    text_pos = rl.Vector2(center_x - text_size.x / 2, center_y - text_size.y / 2)
    rl.draw_text_ex(self._font, label, text_pos, self._font_size, 0, color)
```

### Files Modified

#### `selfdrive/ui/onroad/hud_renderer.py`

1. Add import: `from openpilot.selfdrive.ui.onroad.personality_button import PersonalityButton`
2. In `__init__`: add `self._personality_button: PersonalityButton = PersonalityButton(UI_CONFIG.button_size)`
3. In `_render`: add button rendering (middle-left, 204×204px, only when longitudinal enabled):
   ```python
   if ui_state.has_longitudinal_control:
     personality_size = 300
     personality_x = rect.x + 60
     personality_y = rect.y + (rect.height - personality_size) / 2
     self._personality_button.render(rl.Rectangle(personality_x, personality_y, personality_size, personality_size))
   ```
4. In `user_interacting`: add `or self._personality_button.is_pressed`

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
- **Sync:** Reads personality from `selfdriveState` messages to stay in sync with external changes (e.g., steering wheel button)
