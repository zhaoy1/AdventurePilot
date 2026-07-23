import pytest

from cereal import log

from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import (
  get_follow_buffer_distance,
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


def test_highway_buffer_adds_elasticity_when_gap_is_available():
  v_ego = 31.0
  v_lead = 29.5
  t_follow = get_T_FOLLOW(log.LongitudinalPersonality.standard, v_ego)
  base_gap = get_follow_buffer_distance(v_ego, t_follow)

  tight_gap = base_gap + 2.0
  buffered_gap = base_gap + 18.0

  tight_cost = get_x_ego_obstacle_cost(v_ego, v_lead, d_rel=tight_gap, t_follow=t_follow)
  buffered_cost = get_x_ego_obstacle_cost(v_ego, v_lead, d_rel=buffered_gap, t_follow=t_follow)

  tight_jerk = get_jerk_factor(log.LongitudinalPersonality.standard, v_ego, v_lead=v_lead, d_rel=tight_gap, t_follow=t_follow)
  buffered_jerk = get_jerk_factor(log.LongitudinalPersonality.standard, v_ego, v_lead=v_lead, d_rel=buffered_gap, t_follow=t_follow)

  assert buffered_cost < tight_cost
  assert buffered_jerk > tight_jerk


def test_highway_elasticity_fades_when_closing_speed_is_large():
  v_ego = 31.0
  t_follow = get_T_FOLLOW(log.LongitudinalPersonality.standard, v_ego)
  buffered_gap = get_follow_buffer_distance(v_ego, t_follow) + 18.0

  gentle_cost = get_x_ego_obstacle_cost(v_ego, 29.5, d_rel=buffered_gap, t_follow=t_follow)
  strong_close_cost = get_x_ego_obstacle_cost(v_ego, 24.0, d_rel=buffered_gap, t_follow=t_follow)

  gentle_jerk = get_jerk_factor(log.LongitudinalPersonality.standard, v_ego, v_lead=29.5, d_rel=buffered_gap, t_follow=t_follow)
  strong_close_jerk = get_jerk_factor(log.LongitudinalPersonality.standard, v_ego, v_lead=24.0, d_rel=buffered_gap, t_follow=t_follow)

  assert strong_close_cost > gentle_cost
  assert strong_close_jerk < gentle_jerk
