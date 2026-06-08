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
    self._font_size = 56

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
