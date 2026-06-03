"""Dash dashboard for plotting averaged repeater frequency data."""  # noqa: INP001

from __future__ import annotations

import argparse
import logging
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock, Thread
from typing import Literal

import numpy as np
import plotly.graph_objects as go
import zmq
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html
from plotly.subplots import make_subplots

from saltnz.config import Config, FilterChannel, SumChannel
from saltnz.constants import MSL_AVERAGED_PORT

logger = logging.getLogger(__name__)
MIN_AVERAGED_ROW_VALUES = 2
type Polarisation = Literal["A", "B", "A+B"]
type BinaryPolarisation = Literal["A", "B"]
type PlotMode = Literal["absolute", "configured_offset", "initial_offset"]
TRACE_COLORS: dict[BinaryPolarisation, str] = {"A": "#2563eb", "B": "#dc2626"}
TRACE_DASHES: dict[BinaryPolarisation, str] = {"A": "solid", "B": "solid"}
DEFAULT_PLOT_MODE: PlotMode = "absolute"
DEFAULT_BASELINE_SECONDS = 10.0
MAX_STACKED_PLOTS_WITH_AXIS_TITLES = 3
ABSOLUTE_FREQUENCY_DECIMALS = 6
OFFSET_FREQUENCY_DECIMALS = 3
PLOT_MODE_OPTIONS = [
    {"label": "Beat Freq", "value": "absolute"},
    {"label": "Freq Deviation (/ config beat freq)", "value": "configured_offset"},
    {"label": "Freq Deviation (/ measured avg beat freq)", "value": "initial_offset"},
]


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
        return f"Rep {self.repeater} {self.polarisation} ch {self.channel}"

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


type ChannelSelection = ChannelOption | Sequence[ChannelOption] | None


@dataclass(frozen=True, slots=True)
class RepeaterChoice:
    """A repeater/frequency/range group shown in the dashboard selector."""

    key: str
    repeater: int
    frequency_Hz: float  # noqa: N815
    channel_range: int

    @property
    def label(self) -> str:
        """Return the selector label for this repeater group."""
        return f"Rep {self.repeater}"

    @property
    def detail(self) -> str:
        """Return secondary selector text for this repeater group."""
        return f"{self.frequency_Hz / 1e6:g} MHz | range {self.channel_range}"


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


def binary_polarisation(polarisation: Polarisation) -> BinaryPolarisation | None:
    """Return A/B polarisations while excluding summed channels from the selector."""
    if polarisation in ("A", "B"):
        return polarisation
    return None


def repeater_key(option: ChannelOption) -> str:
    """Return the stable selector key for a repeater/frequency/range group."""
    return f"{option.repeater}|{option.frequency_Hz:.6f}|{option.channel_range}"


def repeater_choices(options: Sequence[ChannelOption]) -> list[RepeaterChoice]:
    """Build the right-hand repeater selector choices from A/B channels."""
    choices: dict[str, RepeaterChoice] = {}
    for option in options:
        if binary_polarisation(option.polarisation) is None:
            continue
        key = repeater_key(option)
        choices.setdefault(
            key,
            RepeaterChoice(
                key=key,
                repeater=option.repeater,
                frequency_Hz=option.frequency_Hz,
                channel_range=option.channel_range,
            ),
        )
    return sorted(
        choices.values(),
        key=lambda choice: (choice.repeater, choice.channel_range, choice.frequency_Hz),
    )


def available_polarisations(options: Sequence[ChannelOption], choice_key: str) -> list[BinaryPolarisation]:
    """Return configured A/B polarisations for a repeater selector row."""
    polarisations = {
        polarisation
        for option in options
        if repeater_key(option) == choice_key
        if (polarisation := binary_polarisation(option.polarisation)) is not None
    }
    return [polarisation for polarisation in ("A", "B") if polarisation in polarisations]


def default_polarisation(options: Sequence[ChannelOption], choice_key: str) -> BinaryPolarisation:
    """Return the default polarisation for a repeater selector row."""
    polarisations = available_polarisations(options, choice_key)
    return "A" if "A" in polarisations else polarisations[0]


def selected_channels(
    options: Sequence[ChannelOption],
    selections: Sequence[tuple[str, BinaryPolarisation]],
) -> list[ChannelOption]:
    """Return configured channels matching selected repeater/polarisation pairs."""
    lookup: dict[tuple[str, BinaryPolarisation], ChannelOption] = {}
    for option in options:
        polarisation = binary_polarisation(option.polarisation)
        if polarisation is None:
            continue
        lookup[(repeater_key(option), polarisation)] = option

    channels: list[ChannelOption] = []
    seen: set[int] = set()
    for key, polarisation in selections:
        option = lookup.get((key, polarisation))
        if option is None or option.average_column in seen:
            continue
        channels.append(option)
        seen.add(option.average_column)
    return channels


def more_than_one_ticked(values: Sequence[Sequence[BinaryPolarisation]]) -> bool:
    """Return whether more than one repeater row has any polarisation selected."""
    return sum(1 for v in values if v) > 1


def select_all_repeaters_values(
    options: Sequence[ChannelOption],
    selector_ids: Sequence[dict[str, str]],
) -> list[list[BinaryPolarisation]]:
    """Return checklist values selecting the default polarisation for every repeater."""
    return [[default_polarisation(options, selector_id["key"])] for selector_id in selector_ids]


def update_repeater_selection_values(
    options: Sequence[ChannelOption],
    triggered_id: object,
    current_values: Sequence[Sequence[BinaryPolarisation]] | None,
    selector_ids: Sequence[dict[str, str]] | None,
) -> list[list[BinaryPolarisation]]:
    """Return updated repeater checklist values."""
    if selector_ids is None:
        return [list(value) for value in (current_values or [])]
    values = [list(value) for value in (current_values or [[] for _ in selector_ids])]
    if triggered_id == "select-all-repeaters":
        if more_than_one_ticked(values):
            values = [[] for _ in selector_ids]
        else:
            values = select_all_repeaters_values(options, selector_ids)
    elif isinstance(triggered_id, dict):
        clicked_key = triggered_id.get("key")
        for index, selector_id in enumerate(selector_ids):
            if selector_id["key"] != clicked_key:
                continue
            selected_default = default_polarisation(options, selector_id["key"])
            if selected_default not in values[index]:
                values[index].insert(0, selected_default)
            break
    return values


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


def normalise_channel_selection(channel: ChannelSelection) -> list[ChannelOption]:
    """Return a list of channels from either the old single-channel or new multi-channel shape."""
    if channel is None:
        return []
    if isinstance(channel, ChannelOption):
        return [channel]
    return list(channel)


def figure_title(channels: Sequence[ChannelOption]) -> str:
    """Return a compact figure title for the selected channels."""
    if not channels:
        return ""
    if len(channels) == 1:
        return channels[0].title
    return ""


def normalise_plot_mode(plot_mode: str | None) -> PlotMode:
    """Return a supported plot mode, defaulting to absolute frequency."""
    if plot_mode == "configured_offset":
        return "configured_offset"
    if plot_mode == "initial_offset":
        return "initial_offset"
    return "absolute"


def normalise_baseline_seconds(seconds: float | None) -> float:
    """Return a finite baseline window length in seconds."""
    if seconds is None:
        return DEFAULT_BASELINE_SECONDS
    seconds_float = float(seconds)
    if not np.isfinite(seconds_float):
        return DEFAULT_BASELINE_SECONDS
    return max(0.0, seconds_float)


def grouped_channels(channels: Sequence[ChannelOption]) -> list[list[ChannelOption]]:
    """Return selected channels grouped by repeater/frequency/range while preserving selection order."""
    groups: dict[str, list[ChannelOption]] = {}
    for channel in channels:
        groups.setdefault(repeater_key(channel), []).append(channel)
    return list(groups.values())


def repeater_panel_title(channels: Sequence[ChannelOption]) -> str:
    """Return a subplot title for one repeater group."""
    channel = channels[0]
    return f"Rep {channel.repeater} | {channel.frequency_Hz / 1e6:g} MHz | range {channel.channel_range}"


def initial_window_baseline_hz(
    timestamps: np.ndarray[tuple[int], np.dtype[np.float64]],
    measured_hz: np.ndarray[tuple[int], np.dtype[np.float64]],
    baseline_seconds: float,
) -> float:
    """Return the mean measured frequency in the first baseline window."""
    if timestamps.size != measured_hz.size:
        finite_indices = np.flatnonzero(np.isfinite(measured_hz))
        return float(measured_hz[finite_indices[0]]) if finite_indices.size else np.nan

    finite = np.isfinite(timestamps) & np.isfinite(measured_hz)
    if not finite.any():
        return np.nan
    first_timestamp = float(timestamps[finite][0])
    baseline_window = finite & (timestamps >= first_timestamp) & (timestamps <= first_timestamp + baseline_seconds)
    if baseline_window.any():
        return float(np.mean(measured_hz[baseline_window]))
    return float(measured_hz[np.flatnonzero(finite)[0]])


def trace_y_values(
    measured_hz: np.ndarray[tuple[int], np.dtype[np.float64]],
    channel: ChannelOption,
    plot_mode: PlotMode,
    timestamps: np.ndarray[tuple[int], np.dtype[np.float64]],
    baseline_seconds: float,
) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    """Return y values transformed for the selected plot mode."""
    if plot_mode == "absolute":
        return np.round(measured_hz / 1e6, ABSOLUTE_FREQUENCY_DECIMALS)
    if plot_mode == "configured_offset":
        return np.round((measured_hz - channel.frequency_Hz) / 1e3, OFFSET_FREQUENCY_DECIMALS)
    baseline_hz = initial_window_baseline_hz(timestamps, measured_hz, baseline_seconds)
    return np.round((measured_hz - baseline_hz) / 1e3, OFFSET_FREQUENCY_DECIMALS)


def y_axis_title(plot_mode: PlotMode) -> str:
    """Return the y-axis title for a plot mode."""
    if plot_mode == "absolute":
        return "Averaged frequency (MHz)"
    return "Frequency Deviation (kHz)"


def y_tick_format(plot_mode: PlotMode) -> str:
    """Return the y-axis tick format for a plot mode."""
    return ".4f" if plot_mode == "absolute" else "+.3f"


def hover_template(plot_mode: PlotMode) -> str:
    """Return the trace hover template for a plot mode."""
    if plot_mode == "absolute":
        return "%{x|%H:%M:%S.%L UTC}<br>%{y:.6f} MHz<extra></extra>"
    return "%{x|%H:%M:%S.%L UTC}<br>%{y:+.3f} kHz<extra></extra>"


def subplot_vertical_spacing(row_count: int) -> float:
    """Return Plotly subplot spacing that stays valid as repeater count grows."""
    if row_count <= 1:
        return 0.0
    return min(0.06, 0.3 / (row_count - 1))


def add_shared_y_axis_label(figure: go.Figure, plot_mode: PlotMode) -> None:
    """Add one y-axis label above stacked plots."""
    figure.add_annotation(
        text=y_axis_title(plot_mode),
        x=0.0,
        y=1.02,
        xref="paper",
        yref="paper",
        xanchor="left",
        yanchor="bottom",
        showarrow=False,
        font={"size": 12, "color": "#475569"},
    )


def make_figure(
    timestamps: list[float],
    rows: np.ndarray[tuple[int, int], np.dtype[np.float64]],
    channel: ChannelSelection,
    plot_mode: str | None = DEFAULT_PLOT_MODE,
    baseline_seconds: float | None = DEFAULT_BASELINE_SECONDS,
) -> go.Figure:
    """Create the live averaged-frequency figure for the selected channels."""
    selected_plot_mode = normalise_plot_mode(plot_mode)
    baseline_window_seconds = normalise_baseline_seconds(baseline_seconds)
    channels = normalise_channel_selection(channel)
    if rows.size == 0:
        empty_channel = channels[0] if len(channels) == 1 else None
        return make_empty_figure("Waiting for averaged data", empty_channel)
    if not channels:
        return make_empty_figure("No channel configured for this selection")
    valid_channels = [channel for channel in channels if channel.average_column < rows.shape[1]]
    if not valid_channels:
        empty_channel = channels[0] if len(channels) == 1 else None
        return make_empty_figure("Selected channel is missing from the averaged-data row", empty_channel)
    times = [datetime.fromtimestamp(timestamp, tz=UTC) for timestamp in timestamps]
    channel_groups = grouped_channels(valid_channels)
    row_count = len(channel_groups)
    subplot_titles = [repeater_panel_title(group) for group in channel_groups] if row_count > 1 else None
    figure = make_subplots(
        rows=row_count,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=subplot_vertical_spacing(row_count),
        subplot_titles=subplot_titles,
    )
    plot_times = np.array(times, dtype=object)
    numeric_timestamps = np.array(timestamps, dtype=float)
    for row_index, group in enumerate(channel_groups, start=1):
        for selected_channel_option in group:
            measured_Hz = rows[:, selected_channel_option.average_column]  # noqa: N806
            y_values = trace_y_values(
                measured_Hz,
                selected_channel_option,
                selected_plot_mode,
                numeric_timestamps,
                baseline_window_seconds,
            )
            finite = np.isfinite(y_values)
            polarisation = binary_polarisation(selected_channel_option.polarisation)
            line = (
                {"color": TRACE_COLORS[polarisation], "dash": TRACE_DASHES[polarisation]}
                if polarisation is not None
                else {}
            )
            figure.add_trace(
                go.Scatter(
                    x=plot_times[finite],
                    y=y_values[finite],
                    mode="lines",
                    name=selected_channel_option.trace_name,
                    line=line,
                    hovertemplate=hover_template(selected_plot_mode),
                ),
                row=row_index,
                col=1,
            )
    figure.update_layout(
        title={"text": figure_title(valid_channels)},
        margin={"l": 64, "r": 24, "t": 56, "b": 56},
        paper_bgcolor="#f8fafc",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        showlegend=len(valid_channels) > 1,
    )
    use_shared_y_axis_label = row_count > MAX_STACKED_PLOTS_WITH_AXIS_TITLES
    if use_shared_y_axis_label:
        add_shared_y_axis_label(figure, selected_plot_mode)
    for row_index in range(1, row_count + 1):
        figure.update_xaxes(
            showgrid=True,
            gridcolor="#e2e8f0",
            zeroline=False,
            row=row_index,
            col=1,
        )
        figure.update_yaxes(
            title={"text": "" if use_shared_y_axis_label else y_axis_title(selected_plot_mode), "standoff": 10},
            tickformat=y_tick_format(selected_plot_mode),
            showgrid=True,
            gridcolor="#e2e8f0",
            zeroline=selected_plot_mode != "absolute",
            zerolinecolor="#94a3b8",
            row=row_index,
            col=1,
        )
    figure.update_xaxes(title="Time", row=row_count, col=1)
    return figure


def create_app(store: AveragedDataStore, options: list[ChannelOption], interval_ms: int) -> Dash:
    """Create the Dash web application."""
    choices = repeater_choices(options)
    if not choices:
        msg = "The config does not contain any averaged channels."
        raise ValueError(msg)
    first_choice = choices[0]
    app = Dash(__name__, title="SALT NZ")
    app.layout = html.Div(
        [
            html.Div(
                [
                    html.H1("SALT NZ", style={"margin": 0, "fontSize": "24px", "fontWeight": 700}),
                    html.Div(
                        "Waiting for data",
                        id="status",
                        style={
                            "color": "#334155",
                            "fontSize": "12px",
                            "fontWeight": 700,
                            "textAlign": "right",
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
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    dcc.RadioItems(
                                        id="plot-mode",
                                        options=PLOT_MODE_OPTIONS,
                                        value=DEFAULT_PLOT_MODE,
                                        inline=True,
                                        inputStyle={"marginRight": "5px"},
                                        labelStyle={
                                            "display": "inline-flex",
                                            "alignItems": "center",
                                            "gap": "4px",
                                            "marginRight": "16px",
                                            "fontSize": "13px",
                                            "fontWeight": 700,
                                            "color": "#334155",
                                            "cursor": "pointer",
                                        },
                                    ),
                                    html.Label(
                                        [
                                            html.Span(
                                                "averaging time (s)",
                                                style={
                                                    "fontSize": "12px",
                                                    "fontWeight": 700,
                                                    "color": "#475569",
                                                },
                                            ),
                                            dcc.Input(
                                                id="baseline-seconds",
                                                type="number",
                                                min=0,
                                                step=1,
                                                value=DEFAULT_BASELINE_SECONDS,
                                                debounce=False,
                                                style={
                                                    "width": "76px",
                                                    "border": "1px solid #cbd5e1",
                                                    "borderRadius": "6px",
                                                    "fontFamily": "inherit",
                                                    "fontSize": "13px",
                                                    "padding": "5px 7px",
                                                },
                                            ),
                                        ],
                                        style={
                                            "display": "inline-flex",
                                            "alignItems": "center",
                                            "gap": "8px",
                                        },
                                    ),
                                ],
                                style={
                                    "display": "flex",
                                    "alignItems": "center",
                                    "justifyContent": "space-between",
                                    "gap": "16px",
                                    "padding": "10px 16px",
                                    "borderBottom": "1px solid #dbe3ec",
                                    "backgroundColor": "#ffffff",
                                },
                            ),
                            dcc.Graph(
                                id="frequency-graph",
                                config={"displayModeBar": True, "responsive": True},
                                style={"height": "100%", "minHeight": "420px"},
                            ),
                        ],
                        style={
                            "display": "grid",
                            "gridTemplateRows": "auto 1fr",
                            "flex": "1 1 auto",
                            "minWidth": 0,
                        },
                    ),
                    html.Aside(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2(
                                                "Repeaters",
                                                style={"margin": 0, "fontSize": "16px", "fontWeight": 700},
                                            ),
                                            html.Button(
                                                "Select all",
                                                id="select-all-repeaters",
                                                type="button",
                                                style={
                                                    "appearance": "none",
                                                    "backgroundColor": "#ffffff",
                                                    "border": "1px solid #cbd5e1",
                                                    "borderRadius": "6px",
                                                    "color": "#334155",
                                                    "cursor": "pointer",
                                                    "fontFamily": "inherit",
                                                    "fontSize": "12px",
                                                    "fontWeight": 700,
                                                    "padding": "5px 8px",
                                                },
                                            ),
                                        ],
                                        style={"display": "flex", "alignItems": "center", "gap": "10px"},
                                    ),
                                    html.Div(
                                        "Polarisation",
                                        style={
                                            "alignSelf": "center",
                                            "fontSize": "16px",
                                            "fontWeight": 700,
                                            "lineHeight": 1.35,
                                            "textAlign": "right",
                                        },
                                    ),
                                ],
                                style={
                                    "display": "grid",
                                    "gap": "12px",
                                    "gridTemplateColumns": "1fr auto",
                                    "padding": "16px",
                                    "borderBottom": "1px solid #dbe3ec",
                                },
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Button(
                                                        choice.label,
                                                        id={"type": "repeater", "key": choice.key},
                                                        type="button",
                                                        style={
                                                            "appearance": "none",
                                                            "background": "transparent",
                                                            "border": 0,
                                                            "color": "#0f172a",
                                                            "cursor": "pointer",
                                                            "fontFamily": "inherit",
                                                            "fontSize": "14px",
                                                            "fontWeight": 700,
                                                            "padding": 0,
                                                            "textAlign": "left",
                                                        },
                                                    ),
                                                    html.Div(
                                                        choice.detail,
                                                        style={"fontSize": "12px", "color": "#64748b"},
                                                    ),
                                                ],
                                                style={"minWidth": 0},
                                            ),
                                            dcc.Checklist(
                                                id={"type": "polarisation", "key": choice.key},
                                                options=[
                                                    {"label": polarisation, "value": polarisation}
                                                    for polarisation in available_polarisations(options, choice.key)
                                                ],
                                                value=(
                                                    [default_polarisation(options, choice.key)]
                                                    if choice == first_choice
                                                    else []
                                                ),
                                                inline=True,
                                                inputStyle={"marginRight": "4px"},
                                                labelStyle={
                                                    "display": "inline-flex",
                                                    "alignItems": "center",
                                                    "gap": "4px",
                                                    "marginLeft": "10px",
                                                    "fontSize": "13px",
                                                    "fontWeight": 700,
                                                    "color": "#334155",
                                                    "cursor": "pointer",
                                                },
                                            ),
                                        ],
                                        style={
                                            "display": "grid",
                                            "gridTemplateColumns": "1fr auto",
                                            "gap": "12px",
                                            "alignItems": "center",
                                            "padding": "10px 12px",
                                            "borderBottom": "1px solid #e2e8f0",
                                        },
                                    )
                                    for choice in choices
                                ],
                                style={"overflowY": "auto"},
                            ),
                        ],
                        style={
                            "width": "300px",
                            "flex": "0 0 300px",
                            "borderLeft": "1px solid #dbe3ec",
                            "backgroundColor": "#ffffff",
                            "display": "grid",
                            "gridTemplateRows": "auto 1fr",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "height": "calc(100vh - 61px)",
                    "minHeight": "480px",
                },
            ),
            dcc.Interval(id="refresh", interval=interval_ms),
        ],
        style={"minHeight": "100vh", "backgroundColor": "#f8fafc", "fontFamily": "Arial, sans-serif"},
    )

    @app.callback(
        Output({"type": "polarisation", "key": ALL}, "value"),
        Input({"type": "repeater", "key": ALL}, "n_clicks"),
        Input("select-all-repeaters", "n_clicks"),
        State({"type": "polarisation", "key": ALL}, "value"),
        State({"type": "polarisation", "key": ALL}, "id"),
        prevent_initial_call=True,
    )
    def select_repeaters(
        _: list[int | None],
        __: int | None,
        current_values: list[list[BinaryPolarisation]] | None,
        selector_ids: list[dict[str, str]] | None,
    ) -> list[list[BinaryPolarisation]]:
        """Update repeater selection from row clicks or the select-all button."""
        return update_repeater_selection_values(options, ctx.triggered_id, current_values, selector_ids)

    @app.callback(
        Output("select-all-repeaters", "children"),
        Input({"type": "polarisation", "key": ALL}, "value"),
    )
    def update_select_all_label(polarisation_values: list[list[BinaryPolarisation]] | None) -> str:
        """Update the select-all button label based on how many repeaters are ticked."""
        return "Deselect all" if more_than_one_ticked(polarisation_values or []) else "Select all"

    @app.callback(
        Output("frequency-graph", "figure"),
        Output("status", "children"),
        Input("refresh", "n_intervals"),
        Input({"type": "polarisation", "key": ALL}, "value"),
        Input("plot-mode", "value"),
        Input("baseline-seconds", "value"),
        State({"type": "polarisation", "key": ALL}, "id"),
    )
    def update_graph(
        _: int,
        selected_polarisations: list[list[BinaryPolarisation]] | None,
        plot_mode: str | None,
        baseline_seconds: float | None,
        selector_ids: list[dict[str, str]] | None,
    ) -> tuple[go.Figure, str]:
        """Refresh the graph and stream status line."""
        timestamps, rows, received, ignored_before_start = store.snapshot()
        selections = [
            (selector_id["key"], polarisation)
            for selector_id, polarisations in zip(selector_ids or [], selected_polarisations or [], strict=False)
            for polarisation in polarisations
        ]
        channels = selected_channels(options, selections)
        figure = make_figure(timestamps, rows, channels, plot_mode, baseline_seconds)
        if timestamps:
            last = datetime.fromtimestamp(timestamps[-1], tz=UTC).strftime("%H:%M:%S UTC")
            status = f"{received} received | {len(timestamps)} shown | {len(channels)} traces | last {last}"
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
    parser.add_argument("--max-points", type=int, default=10000, help="Maximum points to keep in memory.")
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
