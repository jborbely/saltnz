"""Handle data streamed from the FPGA."""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import yaml
import zmq

if TYPE_CHECKING:
    import os


from .constants import FPGA_PORT, MSL_RAMP_PORT, logger


@dataclass(slots=True)
class Config:
    """Configuration for a channel."""

    freq: float
    """The frequency of the ramp in MHz."""

    polarisation: str
    channel: int
    range: int
    repeater: int
    start_index: int = 0

    def __post_init__(self) -> None:
        """Calculate the starting index for the channel."""
        if self.range == 1:
            self.freq = self.freq + 25e6


channels: list[Config] = []


def create_channels(config_path: str | os.PathLike[str]) -> list[Config]:
    """Create channels from the YAML configuration file.

    Args:
        config_path: The path to the YAML configuration file.
    """
    if not channels:

        with Path(config_path).open() as f:
            config = yaml.safe_load(f)
            for c in config["filter_channels"]:
                channels.append(Config(freq=c["freq"], polarisation=c["pol"], channel=c["ch"], range=c["range"], repeater=c["rep"]))

            for c in config["sum_channels"]:
                channels.append(Config(freq=c["freq"], polarisation=c["pol"], channel=c["ch"], range=c["range"], repeater=c["rep"]))

    return channels


def get_shape_from_config(config_path: str | os.PathLike[str]) -> tuple[int, int]:
    """Get the shape of the ramp data from the YAML configuration file.

    Args:
        config_path: The path to the YAML configuration file.
    """
    with Path(config_path).open() as f:
        config = yaml.safe_load(f)
        num_columns = len(config["filter_channels"]) + len(config["sum_channels"])
        num_rows = config["ramp_time_ms"] // config["sampling_time_ms"]
    return num_rows, num_columns


def stream_handler(config_path: str | os.PathLike[str]) -> None:
    """Handle streaming data from the FPGA.

    It receives data from the FPGA every ~10ms.
    It builds an array of frequencies for each ramp and then uses a ZMQ PUB socket to publish the ramp data.

    Args:
        config_path: The path to the YAML configuration file.
    """
    num_rows, num_columns = get_shape_from_config(config_path)

    context = zmq.Context()
    fpga_socket = context.socket(zmq.PULL)
    _ = fpga_socket.connect(f"tcp://127.0.0.1:{FPGA_PORT}")

    msl_socket = context.socket(zmq.PUB)
    _ = msl_socket.bind(f"tcp://127.0.0.1:{MSL_RAMP_PORT}")

    ramp_data = np.full((num_rows, num_columns), dtype=float, fill_value=-1)

    try:
        while True:
            trigger, frequencies = fpga_socket.recv_multipart()
            (bits,) = struct.unpack("I", trigger)
            if bits == 1:
                ramp_data[0] = np.frombuffer(frequencies, dtype=float)
                for i in range(1, num_rows):
                    trigger, frequencies = fpga_socket.recv_multipart()
                    (bits,) = struct.unpack("I", trigger)
                    if bits != 0:
                        logger.critical("Expected trigger bit 1, but got %d. Stopping stream handler", bits)
                        break
                    ramp_data[i] = np.frombuffer(frequencies, dtype=float)
                msl_socket.send(ramp_data)
                logger.info("Received ramp data")
    except KeyboardInterrupt:
        logger.info("Stream handler interrupted by user")

    fpga_socket.close()
    logger.info("FPGA socket closed")
    msl_socket.close()
    logger.info("MSL socket closed")
    context.destroy(linger=1)
    logger.info("ZMQ context terminated")


def ramp_handler(config_path: str | os.PathLike[str]) -> None:
    """Handle ramp data from stream handler.

    Does a ZMQ SUB to subscribe receive the ramp data.

    Args:
        config_path: The path to the YAML configuration file.
    """
    shape = get_shape_from_config(config_path)
    channels = create_channels(config_path)
    for c in channels:
        print(c)

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    _ = socket.connect(f"tcp://127.0.0.1:{MSL_RAMP_PORT}")

    while True:
        try:
            ramp_data = np.frombuffer(socket.recv(), dtype=float).reshape(shape)
            for 
            ramp_data[channels[]]
            logger.info("Received ramp data in ramp handler, %s", shape)
        except KeyboardInterrupt:
            logger.info("Ramp handler interrupted by user")
            break

    socket.close()
    logger.info("ZMQ socket closed")
    context.term()
    logger.info("ZMQ context terminated")
