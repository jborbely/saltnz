"""Mock FPGA implementation for testing/streaming purposes."""

from time import perf_counter, sleep
from typing import TYPE_CHECKING, cast

import numpy as np
import zmq

from .constants import FPGA_PORT, logger

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

    type FPGAData = np.memmap[tuple[int, int], np.dtype[np.float64]]
    from zmq.sugar.context import Context
    from zmq.sugar.socket import SyncSocket


def indices(stop: int, *, start: int = 0, restart: int | None = None) -> Iterator[int]:
    """Generate indices for a range of numbers.

    Args:
        stop: The end of the range (exclusive).
        start: The start of the range (inclusive).
        restart: If provided, the index will reset to this value after reaching `stop`,
            otherwise restart is set to `start`.
    """
    if start >= stop:
        msg = f"start ({start}) must be less than stop ({stop})"
        raise ValueError(msg)

    index = start - 1

    if restart is None:
        restart = start

    if restart >= stop:
        msg = f"restart ({restart}) must be less than stop ({stop})"

        raise ValueError(msg)

    while True:
        index += 1
        if index >= stop:
            index = restart
        yield index


def stream(
    path: str | os.PathLike[str],
    start: int = 0,
    stop: int | None = None,
    restart: int | None = None,
) -> None:
    """Stream data from a file.

    Args:
        path: The path to the file to a `.npy` file.
        start: The starting index for streaming.
        stop: The stopping index for streaming (excluded). If `None`, it will stream until
            the last row for the data in the `.npy` file.
        restart: If provided, the index will reset to this value after reaching `stop`,
            otherwise restart is set to `start`.
    """
    data = cast("FPGAData", np.load(path, mmap_mode="r"))

    context: Context[SyncSocket] = zmq.Context()
    socket: SyncSocket = context.socket(zmq.PUSH)
    _ = socket.bind(f"tcp://127.0.0.1:{FPGA_PORT}")

    if stop is None:
        stop = data.shape[0]

    t0: float = perf_counter()
    for index in indices(stop, start=start, restart=restart):
        triggered = b"\x01\x00\x00\x00" if index % 20 == 1 else b"\x00\x00\x00\x00"
        try:
            _ = socket.send_multipart([triggered, data[index]], flags=zmq.NOBLOCK)  # pyright: ignore[reportUnknownMemberType]
        except zmq.Again:
            logger.debug("No receiver available, skipping index %d", index)

        try:
            sleep(max(0, 0.01 - (perf_counter() - t0)))
        except KeyboardInterrupt:
            logger.info("Streaming interrupted by user")
            break

        t0 = perf_counter()

    socket.close()
    context.term()
    logger.info("ZMQ socket closed and context terminated")
