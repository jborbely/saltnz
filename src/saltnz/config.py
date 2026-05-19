"""Represents a YAML configuration file."""

from dataclasses import dataclass
from enum import Enum
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .constants import DISCARD_MARGIN_SAMPLES, FPGA_INTERCEPT_MHZ, SWEEP_RATE_MHZ_PER_MS, WRAPPED_RANGE_OFFSET_MHZ

if TYPE_CHECKING:
    import os
    from typing import Any, Literal


class Config:
    """Loads the configuration from a YAML file."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        """Loads the configuration from a YAML file.

        Args:
            path: The path to the YAML configuration file.
        """
        self.path: Path[str] = Path(path)
        """The path to the YAML configuration file."""

        with self.path.open() as f:
            cfg: dict[str, Any] = yaml.safe_load(f)

        self.measurement_type: MeasurementType = MeasurementType(cfg["measurement_type"])
        """The type of measurement that the FPGA is configured to perform."""

        self.ramp_time_ms: int = cfg["ramp_time_ms"]
        """The ramp duration, in milliseconds."""

        self.sampling_time_ms: int = cfg["sampling_time_ms"]
        """The duration, in milliseconds, that the FPGA acquires frequency data."""

        self.filter_channels: list[FilterChannel] = [
            FilterChannel(
                channel=channel["ch"],
                freq=channel["freq"],
                polarisation=channel["pol"],
                range=channel["range"],
                repeater=channel["rep"],
            )
            for channel in cfg["filter_channels"]
        ]
        """Information about the filtered channels."""

        for channel in self.filter_channels:
            calculate_start_index(channel, self)

        self.sum_channels: list[SumChannel] = [
            SumChannel(
                channel=channel["ch"],
                freq=channel["freq"],
                polarisation=channel["pol"],
                range=channel["range"],
                repeater=channel["rep"],
                sum_of=channel["sumof"],
                sampling_time_ms=self.sampling_time_ms,
            )
            for channel in cfg["sum_channels"]
        ]
        """Information about the summed filtered channels."""

        for channel in self.sum_channels:
            calculate_start_index(channel, self)

    def __repr__(self) -> str:
        """Returns the string representation of the Config object."""
        return f"Config(path={self.path.resolve()})"

    def array_shape(self) -> tuple[int, int]:
        """Returns the shape of the numpy array for the data transferred for a ramp.

        Returns:
            A tuple containing the number of rows and columns of the numpy array.
        """
        num_rows = self.ramp_time_ms // self.sampling_time_ms
        num_columns = len(self.filter_channels) + len(self.sum_channels)
        return num_rows, num_columns


class MeasurementType(Enum):
    """The type of measurement that the FPGA is configured to perform."""

    V1 = "V1"
    V2 = "V2"


@dataclass(kw_only=True, slots=True)
class FilterChannel:
    """Represents a channel that is filtered in the measurement."""

    channel: int
    """The channel number."""

    freq: float
    """The frequency of the channel in MHz."""

    polarisation: Literal["A", "B"]
    """Polarization type: A or B."""

    range: int
    """The signal from the dual-polarisation receiver is split into `ranges` using analogue filters before sampling."""

    repeater: int
    """The repeater number that the channel is associated with."""

    start_index: int = 0
    """The index of the first *good* sample to be used for this channel."""


@dataclass(kw_only=True, slots=True)
class SumChannel:
    """Represents a sum of two filtered channels for A+B polarisation."""

    channel: int
    """The channel number."""

    freq: float
    """The frequency of the channel in MHz."""

    polarisation: Literal["A+B"]
    """Polarization type: A+B."""

    range: int
    """The signal from the dual-polarisation receiver is split into `ranges` using analogue filters before sampling."""

    repeater: int
    """The repeater number that the channel is associated with."""

    sampling_time_ms: int
    """The duration, in milliseconds, that the FPGA acquires frequency data for this channel."""

    sum_of: list[int]
    """The channel numbers of the two filtered channels that are summed to create this channel."""

    start_index: int = 0
    """The index of the first *good* sample to be used for this channel."""


def calculate_start_index(channel: FilterChannel | SumChannel, config: Config) -> None:
    """Calculate the starting index for the channel.

    Args:
        channel: The channel for which to calculate the starting index.
        config: The configuration object containing the measurement type and sampling time.
    """
    if config.measurement_type == MeasurementType.V1:
        true_freq = channel.freq + WRAPPED_RANGE_OFFSET_MHZ if channel.range == 1 else channel.freq
        delay_samples = (true_freq - FPGA_INTERCEPT_MHZ) / SWEEP_RATE_MHZ_PER_MS / config.sampling_time_ms
        n_discard = ceil(delay_samples)
        if n_discard - delay_samples <= DISCARD_MARGIN_SAMPLES:
            n_discard += 1
        channel.start_index = n_discard
    else:
        msg = f"Measurement type {config.measurement_type} is not supported yet."
        raise NotImplementedError(msg)
