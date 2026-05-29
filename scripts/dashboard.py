"""Dash dashboard for plotting averaged repeater frequency data."""  # noqa: INP001

from __future__ import annotations

import argparse
import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock, Thread
from typing import Literal

import numpy as np
import plotly.graph_objects as go
import zmq
from dash import Dash, Input, Output, dcc, html

from saltnz.config import Config, FilterChannel, SumChannel
from saltnz.constants import MSL_AVERAGED_PORT

logger = logging.getLogger(__name__)
MIN_AVERAGED_ROW_VALUES = 2
type Polarisation = Literal["A", "B", "A+B"]


@dataclass(frozen=True, slots=True)
class ChannelOption:
    """A configured averaged-data column that can be plotted."""

    repeater: int
    polarisation: Polarisation
    channel: int
    average_column: int
    frequency_Hz: float  # noqa: N815
    channel_range: int

    @property
    def trace_name(self) -> str:
        """Return a compact display name for this channel."""
        return "Frequency"

    @property
    def title(self) -> str:
        """Return the display title for this channel."""
        return (
            f"rep {self.repeater} | ch {self.channel} | freq {self.frequency_Hz / 1e6:g} MHz | "
            f"polar {self.polarisation} | range {self.channel_range}"
        )

    @property
    def dropdown_label(self) -> str:
        """Return the channel selector label."""
        return str(self.channel)


class AveragedDataStore:
    """Thread-safe rolling store for averaged frequency rows."""

    def __init__(self, max_points: int, start_time: float) -> None:
        """Create a rolling store limited to `max_points` rows."""
        self._timestamps: deque[float] = deque(maxlen=max_points)
        self._rows: deque[np.ndarray[tuple[int], np.dtype[np.float64]]] = deque(maxlen=max_points)
        self._lock = Lock()
        self._received = 0
        self._ignored_before_start = 0
        self._start_time = start_time

    def append(self, row: np.ndarray[tuple[int], np.dtype[np.float64]]) -> None:
        """Append one row from the averaged-data stream."""
        timestamp = float(row[0])
        with self._lock:
            if timestamp < self._start_time:
                self._ignored_before_start += 1
                return
            self._timestamps.append(timestamp)
            self._rows.append(row.copy())
            self._received += 1

    def snapshot(self) -> tuple[list[float], np.ndarray[tuple[int, int], np.dtype[np.float64]], int, int]:
        """Return a consistent snapshot of the rolling data."""
        with self._lock:
            timestamps = list(self._timestamps)
            rows = list(self._rows)
            received = self._received
            ignored_before_start = self._ignored_before_start
        if not rows:
            return timestamps, np.empty((0, 0), dtype=float), received, ignored_before_start
        return timestamps, np.vstack(rows), received, ignored_before_start


def channel_options(config: Config) -> list[ChannelOption]:
    """Build dashboard channel options from the filter channels in the config."""
    options: list[ChannelOption] = []
    for index, channel in enumerate(config.filter_channels):
        if not isinstance(channel, FilterChannel):
            continue
        options.append(
            ChannelOption(
                repeater=channel.repeater,
                polarisation=channel.polarisation,
                channel=channel.channel,
                average_column=index + 1,
                frequency_Hz=channel.freq,
                channel_range=channel.range,
            )
        )
    offset = len(config.filter_channels)
    for index, channel in enumerate(config.sum_channels, start=offset):
        if not isinstance(channel, SumChannel):
            continue
        options.append(
            ChannelOption(
                repeater=channel.repeater,
                polarisation=channel.polarisation,
                channel=channel.channel,
                average_column=index + 1,
                frequency_Hz=channel.freq,
                channel_range=channel.range,
            )
        )
    return options


def subscribe_to_averages(store: AveragedDataStore, host: str, port: int) -> None:
    """Subscribe to averaged frequency rows and add them to the store."""
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    socket.setsockopt(zmq.CONFLATE, 1)
    socket.connect(f"tcp://{host}:{port}")
    logger.info("Subscribed to averaged data on tcp://%s:%d", host, port)
    try:
        while True:
            message = socket.recv()
            logger.info("received averaged data")
            try:
                row = np.frombuffer(message, dtype=float).copy()
            except ValueError:
                logger.exception("Ignored malformed averaged-data message with %d bytes", len(message))
                continue
            if row.size >= MIN_AVERAGED_ROW_VALUES:
                store.append(row)
            else:
                logger.warning("Ignored short averaged-data row with %d values", row.size)
    finally:
        socket.close()
        context.term()


def selected_channel(options: list[ChannelOption], channel_number: int | None) -> ChannelOption | None:
    """Return the selected configured channel."""
    sorted_options = sorted(options, key=lambda option: option.channel)
    if not sorted_options:
        return None
    if channel_number is None:
        return sorted_options[0]
    return next((option for option in sorted_options if option.channel == channel_number), sorted_options[0])


def make_empty_figure(message: str, channel: ChannelOption | None = None) -> go.Figure:
    """Create a graph figure with a centered status annotation."""
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16, "color": "#64748b"},
    )
    figure.update_layout(
        title={"text": channel.title if channel else ""},
        margin={"l": 64, "r": 24, "t": 56, "b": 56},
        paper_bgcolor="#f8fafc",
        plot_bgcolor="#ffffff",
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


def make_figure(
    timestamps: list[float],
    rows: np.ndarray[tuple[int, int], np.dtype[np.float64]],
    channel: ChannelOption | None,
) -> go.Figure:
    """Create the live averaged-frequency figure for the selected channel."""
    if rows.size == 0:
        return make_empty_figure("Waiting for averaged data", channel)
    if channel is None:
        return make_empty_figure("No channel configured for this selection")
    if channel.average_column >= rows.shape[1]:
        return make_empty_figure("Selected channel is missing from the averaged-data row", channel)
    times = [datetime.fromtimestamp(timestamp, tz=UTC) for timestamp in timestamps]
    figure = go.Figure()
    measured_Hz = rows[:, channel.average_column]  # noqa: N806
    finite = np.isfinite(measured_Hz)
    figure.add_trace(
        go.Scatter(
            x=np.array(times, dtype=object)[finite],
            y=measured_Hz[finite],
            mode="lines",
            name=channel.trace_name,
            hovertemplate="%{x|%H:%M:%S.%L UTC}<br>%{y:.6f} Hz<extra></extra>",
        )
    )
    figure.update_layout(
        title={"text": channel.title},
        margin={"l": 64, "r": 24, "t": 56, "b": 56},
        paper_bgcolor="#f8fafc",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        showlegend=False,
        xaxis={
            "title": "Time",
            "showgrid": True,
            "gridcolor": "#e2e8f0",
            "zeroline": False,
        },
        yaxis={
            "title": "Averaged frequency (Hz)",
            "showgrid": True,
            "gridcolor": "#e2e8f0",
            "zeroline": False,
        },
    )
    return figure


def create_app(store: AveragedDataStore, options: list[ChannelOption], interval_ms: int) -> Dash:
    """Create the Dash web application."""
    sorted_options = sorted(options, key=lambda option: option.channel)
    if not sorted_options:
        msg = "The config does not contain any averaged channels."
        raise ValueError(msg)
    first_channel = selected_channel(sorted_options, None)
    app = Dash(__name__, title="SALT NZ")
    app.layout = html.Div(
        [
            html.Div(
                [
                    html.H1("SALT NZ", style={"margin": 0, "fontSize": "24px", "fontWeight": 700}),
                    html.Div(
                        [
                            html.Label(
                                [
                                    html.Span("Channel", style={"display": "block", "fontSize": "12px"}),
                                    dcc.Dropdown(
                                        id="channel",
                                        options=[
                                            {"label": channel.dropdown_label, "value": channel.channel}
                                            for channel in sorted_options
                                        ],
                                        value=first_channel.channel if first_channel else None,
                                        clearable=False,
                                        searchable=True,
                                        style={"minWidth": "180px"},
                                    ),
                                ],
                                style={"display": "block"},
                            ),
                        ],
                        style={
                            "display": "flex",
                            "gap": "24px",
                            "alignItems": "end",
                            "flexWrap": "wrap",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "gap": "24px",
                    "padding": "18px 24px",
                    "borderBottom": "1px solid #dbe3ec",
                    "backgroundColor": "#ffffff",
                },
            ),
            dcc.Graph(
                id="frequency-graph",
                config={"displayModeBar": True, "responsive": True},
                style={"height": "calc(100vh - 124px)", "minHeight": "420px"},
            ),
            html.Div(
                id="status",
                style={
                    "position": "fixed",
                    "right": "18px",
                    "bottom": "14px",
                    "padding": "6px 10px",
                    "border": "1px solid #cbd5e1",
                    "borderRadius": "6px",
                    "backgroundColor": "rgba(255, 255, 255, 0.92)",
                    "color": "#334155",
                    "fontSize": "12px",
                },
            ),
            dcc.Interval(id="refresh", interval=interval_ms),
        ],
        style={"minHeight": "100vh", "backgroundColor": "#f8fafc", "fontFamily": "Arial, sans-serif"},
    )

    @app.callback(
        Output("frequency-graph", "figure"),
        Output("status", "children"),
        Input("refresh", "n_intervals"),
        Input("channel", "value"),
    )
    def update_graph(
        _: int,
        channel_number: int | None,
    ) -> tuple[go.Figure, str]:
        """Refresh the graph and stream status line."""
        timestamps, rows, received, ignored_before_start = store.snapshot()
        channel = selected_channel(options, channel_number)
        figure = make_figure(timestamps, rows, channel)
        if timestamps:
            last = datetime.fromtimestamp(timestamps[-1], tz=UTC).strftime("%H:%M:%S UTC")
            status = f"{received} received | {len(timestamps)} shown | last {last}"
        else:
            status = "Waiting for data"
        if ignored_before_start:
            status = f"{status} | {ignored_before_start} old ignored"
        return figure, status

    return app


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Live dashboard for averaged SALT repeater frequency data.")
    parser.add_argument("config_path", help="Path to the YAML configuration file.")
    parser.add_argument("--data-host", default="127.0.0.1", help="Averaged data ZMQ host.")
    parser.add_argument("--data-port", type=int, default=MSL_AVERAGED_PORT, help="Averaged data ZMQ port.")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard HTTP host.")
    parser.add_argument("--port", type=int, default=8050, help="Dashboard HTTP port.")
    parser.add_argument("--max-points", type=int, default=3000, help="Maximum points to keep in memory.")
    parser.add_argument("--interval-ms", type=int, default=1000, help="Graph refresh interval in milliseconds.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and Dash debug mode.")
    return parser.parse_args()


def main() -> None:
    """Run the dashboard."""
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    config = Config(args.config_path)
    options = channel_options(config)
    store = AveragedDataStore(max_points=args.max_points, start_time=datetime.now(UTC).timestamp())
    subscriber = Thread(target=subscribe_to_averages, args=(store, args.data_host, args.data_port), daemon=True)
    subscriber.start()
    app = create_app(store=store, options=options, interval_ms=args.interval_ms)
    logger.info("Open http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
