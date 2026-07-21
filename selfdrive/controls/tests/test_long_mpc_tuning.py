import pytest

from cereal import log

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import (
  get_T_FOLLOW,
  get_jerk_factor,
  get_lead_danger_factor,
  get_x_ego_obstacle_cost,
)


def test_auto_personality_keeps_existing_speed_split_behavior():
  local_speed = 20.0
  highway_speed = 30.0

  assert get_T_FOLLOW(log.LongitudinalPersonality.relaxed, local_speed) == pytest.approx(
    get_T_FOLLOW(log.LongitudinalPersonality.standard, local_speed)
  )
  assert get_jerk_factor(log.LongitudinalPersonality.relaxed, local_speed) == pytest.approx(
    get_jerk_factor(log.LongitudinalPersonality.standard, local_speed)
  )

  assert get_T_FOLLOW(log.LongitudinalPersonality.relaxed, highway_speed) == pytest.approx(
    get_T_FOLLOW(log.LongitudinalPersonality.aggressive, highway_speed)
  )
  assert get_jerk_factor(log.LongitudinalPersonality.relaxed, highway_speed) == pytest.approx(
    get_jerk_factor(log.LongitudinalPersonality.aggressive, highway_speed)
  )


def test_lead_danger_factor_increases_with_closing_speed():
  matched_speed = get_lead_danger_factor(30.0, 30.0)
  gentle_close = get_lead_danger_factor(30.0, 27.0)
  strong_close = get_lead_danger_factor(30.0, 22.0)

  assert matched_speed == pytest.approx(0.8)
  assert matched_speed < gentle_close < strong_close <= 0.92


def test_obstacle_cost_stays_elastic_when_matched_and_rises_when_closing():
  no_lead = get_x_ego_obstacle_cost(30.0)
  matched_speed = get_x_ego_obstacle_cost(30.0, 30.0)
  gentle_close = get_x_ego_obstacle_cost(30.0, 27.0)
  strong_close = get_x_ego_obstacle_cost(30.0, 22.0)

  assert matched_speed == pytest.approx(no_lead)
  assert matched_speed < gentle_close < strong_close
