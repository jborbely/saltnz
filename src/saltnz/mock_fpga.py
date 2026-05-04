"""Mock FPGA implementation for testing/streaming purposes."""

import logging
from time import perf_counter, sleep
from typing import TYPE_CHECKING, cast

import numpy as np
import zmq

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
    trigger: int = 0,
) -> None:
    """Stream data from a file.

    Args:
        path: The path to the file to a `.npy` file.
        start: The starting index for streaming.
        stop: The stopping index for streaming (excluded). If `None`, it will stream until
            the last row for the data in the `.npy` file.
        restart: If provided, the index will reset to this value after reaching `stop`,
            otherwise restart is set to `start`.
        trigger: The index at which to send a trigger signal (modulo 20).
    """
    data = cast("FPGAData", np.load(path, mmap_mode="r"))

    context: Context[SyncSocket] = zmq.Context()
    pusher: SyncSocket = context.socket(zmq.PUSH)
    _ = pusher.bind("tcp://127.0.0.1:5555")

    if stop is None:
        stop = data.shape[0]

    t0: float = perf_counter()
    for index in indices(stop, start=start, restart=restart):
        triggered = b"\x01" if index % 20 == trigger else b"\x00"
        _ = pusher.send_multipart([triggered, data[index].tobytes()])  # pyright: ignore[reportAny, reportUnknownMemberType]
        sleep(max(0, 0.01 - (perf_counter() - t0)))
        t0 = perf_counter()


def stream_handler() -> None:
    """Handle streaming data from the FPGA."""
    context: Context[SyncSocket] = zmq.Context()
    puller: SyncSocket = context.socket(zmq.PULL)
    _ = puller.connect("tcp://127.0.0.1:5555")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    while True:
        trigger, sample = puller.recv_multipart()
        logging.info(f"Received trigger: {trigger}, sample: {sample[:10]}...")
