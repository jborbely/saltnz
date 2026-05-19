from typing import TYPE_CHECKING

import pytest

from saltnz.config import MeasurementType

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture(autouse=True)
def create_config(tmp_path: Path[str]) -> Callable[[MeasurementType], Path[str]]:
    """Fixture that provides a default configuration for tests."""
    file = tmp_path / "config.yml"

    def create(measurement_type: MeasurementType = MeasurementType.V1) -> Path[str]:
        with file.open("w") as f:
            f.write(
                f"""measurement_type: {measurement_type.value}
ramp_time_ms: 200
sampling_time_ms: 10
filter_channels:
- adc: 0
  att: 15
  ch: 0
  comb: null
  dds_freq: 2.6458740234375
  dds_pinc: 578
  dds_qinv: true
  freq: 2.645
  lp: null
  pbw: 0.1
  pol: A
  range: 0
  rep: 0
  sbw: 0.25
  th: 1
  wl: 1567.13
sum_channels:
- ch: 122
  comb: null
  dds_freq: 8.477783203125
  dds_pinc: 1852
  dds_qinv: true
  freq: 8.48
  lp: null
  pol: A+B
  range: 0
  rep: 7
  sumof:
  - 14
  - 15
  th: 1
  wl: 1567.13
"""
            )

    return create
