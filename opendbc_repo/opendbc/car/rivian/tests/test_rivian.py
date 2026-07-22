import unittest

from opendbc.car.rivian.interface import CarInterface
from opendbc.car.rivian.fingerprints import FW_VERSIONS
from opendbc.car.rivian.values import CAR, FW_QUERY_CONFIG, WMI, ModelLine, ModelYear


class TestRivian(unittest.TestCase):
  def test_custom_fuzzy_fingerprinting(self):
    for platform in CAR:
      with self.subTest(platform=platform.name):
        for wmi in WMI:
          for line in ModelLine:
            for year in ModelYear:
              for bad in (True, False):
                vin = ["0"] * 17
                vin[:3] = wmi
                vin[3] = line.value
                vin[9] = year.value
                if bad:
                  vin[3] = "Z"
                vin = "".join(vin)

                matches = FW_QUERY_CONFIG.match_fw_to_car_fuzzy({}, vin, FW_VERSIONS)
                should_match = year in platform.config.years and not bad
                assert (matches == {platform}) == should_match, "Bad match"

  def test_stop_tuning_is_comfort_biased(self):
    car_params = CarInterface.get_non_essential_params(CAR.RIVIAN_R1)

    self.assertAlmostEqual(car_params.vEgoStopping, 0.4)
    self.assertAlmostEqual(car_params.stopAccel, -0.35)
    self.assertAlmostEqual(car_params.stoppingDecelRate, 0.25)
