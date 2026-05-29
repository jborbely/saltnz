from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

from saltnz.config import Config

DASHBOARD_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dashboard.py"
SPEC = importlib.util.spec_from_file_location("dashboard_under_test", DASHBOARD_PATH)
if SPEC is None or SPEC.loader is None:
    msg = f"Could not load dashboard module from {DASHBOARD_PATH}"
    raise ImportError(msg)

dashboard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dashboard
SPEC.loader.exec_module(dashboard)

ChannelOption = dashboard.ChannelOption
AveragedDataStore = dashboard.AveragedDataStore
channel_options = dashboard.channel_options
selected_channel = dashboard.selected_channel
make_figure = dashboard.make_figure


def test_channel_options_include_filter_and_sum_columns(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """measurement_type: V1
ramp_time_ms: 200
sampling_time_ms: 10
filter_channels:
- ch: 14
  freq: 8.48
  pol: A
  range: 0
  rep: 7
- ch: 15
  freq: 8.48
  pol: B
  range: 0
  rep: 7
sum_channels:
- ch: 122
  freq: 8.48
  pol: A+B
  range: 0
  rep: 7
  sumof:
  - 14
  - 15
""",
    )
    config = Config(config_path)

    options = channel_options(config)

    assert options == [
        ChannelOption(
            repeater=7,
            polarisation="A",
            channel=14,
            average_column=1,
            frequency_Hz=8.48e6,
            channel_range=0,
        ),
        ChannelOption(
            repeater=7,
            polarisation="B",
            channel=15,
            average_column=2,
            frequency_Hz=8.48e6,
            channel_range=0,
        ),
        ChannelOption(
            repeater=7,
            polarisation="A+B",
            channel=122,
            average_column=3,
            frequency_Hz=8.48e6,
            channel_range=0,
        ),
    ]


def test_selected_channel_uses_channel_number() -> None:
    options = [
        ChannelOption(
            repeater=7,
            polarisation="A",
            channel=14,
            average_column=1,
            frequency_Hz=8.48e6,
            channel_range=0,
        ),
        ChannelOption(
            repeater=7,
            polarisation="A",
            channel=15,
            average_column=2,
            frequency_Hz=8.48e6,
            channel_range=0,
        ),
    ]

    assert selected_channel(options, channel_number=15) == options[1]


def test_make_figure_plots_raw_averaged_frequency_from_hz_stream() -> None:
    channel = ChannelOption(
        repeater=0,
        polarisation="A",
        channel=0,
        average_column=1,
        frequency_Hz=2.645e6,
        channel_range=0,
    )

    figure = make_figure(
        timestamps=[1.0],
        rows=np.array([[1.0, 2_645_266.63212162]]),
        channel=channel,
    )

    np.testing.assert_allclose(figure.data[0].y[0], 2_645_266.63212162)


def test_store_ignores_rows_timestamped_before_dashboard_start() -> None:
    store = AveragedDataStore(max_points=10, start_time=100.0)

    store.append(np.array([99.0, 1.0]))
    store.append(np.array([100.0, 2.0]))

    timestamps, rows, received, ignored_before_start = store.snapshot()

    assert timestamps == [100.0]
    np.testing.assert_allclose(rows, np.array([[100.0, 2.0]]))
    assert received == 1
    assert ignored_before_start == 1
