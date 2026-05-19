"""Handle data streamed from the FPGA."""

import struct
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np
import zmq

from .constants import FPGA_PORT, MSL_RAMP_PORT, logger

if TYPE_CHECKING:
    from .config import Config


def stream_handler(config: Config) -> None:
    """Handle streaming data from the FPGA.

    It receives data from the FPGA every `config.sampling_time_ms` milliseconds.
    It builds an array of frequencies for each ramp and then uses a ZMQ PUB socket to publish the ramp data.

    Args:
        config: The configuration object.
    """
    num_rows, num_columns = config.array_shape()

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
                t0 = struct.pack("d", datetime.now(UTC).timestamp())
                ramp_data[0] = np.frombuffer(frequencies, dtype=float)
                for i in range(1, num_rows):
                    trigger, frequencies = fpga_socket.recv_multipart()
                    (bits,) = struct.unpack("I", trigger)
                    if bits != 0:
                        logger.critical("Expected trigger bit 1, but got %d. Stopping stream handler", bits)
                        break
                    ramp_data[i] = np.frombuffer(frequencies, dtype=float)
                msl_socket.send_multipart([t0, ramp_data])
    except KeyboardInterrupt:
        logger.info("FPGA stream handler interrupted by user")

    fpga_socket.close()
    logger.info("FPGA socket closed")
    msl_socket.close()
    logger.info("MSL socket closed")
    context.destroy(linger=1)
    logger.info("ZMQ context terminated")


def ramp_handler(config: Config) -> None:
    """Handle ramp data from stream handler.

    Does a ZMQ SUB to subscribe receive the ramp data.

    Args:
        config: The configuration object.
    """
    shape = config.array_shape()
    num_columns = shape[1]

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    _ = socket.connect(f"tcp://127.0.0.1:{MSL_RAMP_PORT}")

    try:
        while True:
            t0, data = socket.recv_multipart()
            trigger_time = struct.unpack("d", t0)[0]
            ramp_data = np.frombuffer(data, dtype=float).reshape(shape)
            # averaged = np.array([

            #     for i in range(num_columns)

            # ])
            #  :
            for i in range(num_columns):
                ch = config.filter_channels[i]
                ramp_data[ch.start_index :, i]

            logger.info("Received ramp data in ramp handler, %s, %s", trigger_time, shape)
    except KeyboardInterrupt:
        logger.info("Ramp handler interrupted by user")

    socket.close()
    logger.info("ZMQ socket closed")
    context.term()
    logger.info("ZMQ context terminated")
