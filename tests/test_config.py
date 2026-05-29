from typing import TYPE_CHECKING

import pytest

from saltnz.config import Config, FilterChannel, MeasurementType, SumChannel, v1_calculate_start_index

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("freq", "rng", "expected"),
    [
        (2.645e6, 0, 1),
        (13.7e6, 0, 2),
        (25.82e6, 0, 2),
        (0.82e6, 1, 2),
        (14.14e6, 1, 4),
        (24.37e6, 1, 4),
    ],
)
def test_v1_calculate_start_index_filter_channel(freq: float, rng: int, expected: int) -> None:
    channel = FilterChannel(channel=0, freq=freq, polarisation="A", range=rng, repeater=0)
    v1_calculate_start_index(channel, sampling_time_ms=10)
    assert channel.start_index == expected  # The expected value assumes DISCARD_MARGIN_SAMPLES = 0.1


def test_load(tmp_path: Path) -> None:
    tmp_file = tmp_path / "config.yaml"
    content = (
        "adc_sampling: 300000000.0\n"
        "dac_sampling: 600000000.0\n"
        "dds_phase_width: 16\n"
        "extracted_from: /somewhere.txt\n"
        "filter_channels:\n"
        "- adc: 0\n"
        "  att: 15\n"
        "  ch: 14\n"
        "  comb: null\n"
        "  dds_freq: 8.477783203125\n"
        "  dds_pinc: 1852\n"
        "  dds_qinv: true\n"
        "  freq: 8.48\n"
        "  lp: null\n"
        "  pbw: 0.1\n"
        "  pol: A\n"
        "  range: 0\n"
        "  rep: 7\n"
        "  sbw: 0.25\n"
        "  th: 1\n"
        "  wl: 1567.13\n"
        "- adc: 2\n"
        "  att: 15\n"
        "  ch: 15\n"
        "  comb: null\n"
        "  dds_freq: 8.477783203125\n"
        "  dds_pinc: 1852\n"
        "  dds_qinv: true\n"
        "  freq: 8.48\n"
        "  lp: null\n"
        "  pbw: 0.1\n"
        "  pol: B\n"
        "  range: 0\n"
        "  rep: 7\n"
        "  sbw: 0.25\n"
        "  th: 1\n"
        "  wl: 1567.13\n"
        "measurement_type: V1\n"
        "num_adcs: 4\n"
        "ramp_time_ms: 120\n"
        "sampling_time_ms: 6\n"
        "sum_channels:\n"
        "- ch: 122\n"
        "  comb: null\n"
        "  dds_freq: 8.477783203125\n"
        "  dds_pinc: 1852\n"
        "  dds_qinv: true\n"
        "  freq: 8.48\n"
        "  lp: null\n"
        "  pol: A+B\n"
        "  range: 0\n"
        "  rep: 7\n"
        "  sumof:\n"
        "  - 14\n"
        "  - 15\n"
        "  th: 1\n"
        "  wl: 1567.13\n"
        "summing: true\n"
    )
    tmp_file.write_text(content)

    config = Config(tmp_file)
    assert config.measurement_type == MeasurementType.V1
    assert config.ramp_time_ms == 120
    assert config.sampling_time_ms == 6
    assert len(config.filter_channels) == 2
    assert config.filter_channels[0] == FilterChannel(
        channel=14,
        freq=8.48e6,
        polarisation="A",
        range=0,
        repeater=7,
        start_index=1,  # This value assumes DISCARD_MARGIN_SAMPLES = 0.1
    )
    assert config.filter_channels[1] == FilterChannel(
        channel=15,
        freq=8.48e6,
        polarisation="B",
        range=0,
        repeater=7,
        start_index=1,  # This value assumes DISCARD_MARGIN_SAMPLES = 0.1
    )
    assert len(config.sum_channels) == 1
    assert config.sum_channels[0] == SumChannel(
        channel=122,
        freq=8.48e6,
        polarisation="A+B",
        range=0,
        repeater=7,
        sampling_time_ms=6,
        sum_of=[14, 15],
        start_index=1,  # This value assumes DISCARD_MARGIN_SAMPLES = 0.1
    )

    assert str(config) == f"Config(path={tmp_file.resolve()})"
    assert config.array_shape() == (20, 3)


def test_load_measurement_type_not_implemented(tmp_path: Path) -> None:
    tmp_file = tmp_path / "config.yaml"
    content = (
        "adc_sampling: 300000000.0\n"
        "dac_sampling: 600000000.0\n"
        "dds_phase_width: 16\n"
        "extracted_from: /somewhere.txt\n"
        "filter_channels: []\n"
        "measurement_type: V2\n"
        "num_adcs: 4\n"
        "ramp_time_ms: 123\n"
        "sampling_time_ms: 6\n"
        "sum_channels: []\n"
        "summing: true\n"
    )
    tmp_file.write_text(content)

    with pytest.raises(NotImplementedError):
        _ = Config(tmp_file)
