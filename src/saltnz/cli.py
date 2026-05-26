"""Command line interface for the saltnz package."""

import logging
from typing import Annotated

import typer

from .config import Config
from .handle_fpga import ramp_handler, stream_handler
from .mock_fpga import stream

app = typer.Typer(name="salt")


@app.command(help="Mock the FPGA data stream using a numpy file.")
def mock(
    *,
    path: Annotated[str, typer.Argument(help="The path to a numpy file containing the mock data.")],
    config_path: Annotated[str, typer.Argument(help="The path to a YAML configuration file.")],
    start: Annotated[int, typer.Option(help="The starting index of the data to stream.")] = 0,
    stop: Annotated[
        int | None,
        typer.Option(
            help="The stopping index of the data to stream (excluded). If not provided the length of the array is used."
        ),
    ] = None,
    restart: Annotated[
        int | None,
        typer.Option(
            help="The index to restart the stream from. If not provided, it will restart from the `start` index."
        ),
    ] = None,
    debug: Annotated[bool, typer.Option(help="Enable debug logging.")] = False,
) -> None:
    """Mock the FPGA data stream using a numpy file."""
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    stream(path=path, config=Config(config_path), start=start, stop=stop, restart=restart)


@app.command(help="Handle the FPGA data stream in real time.")
def handler(
    *,
    path: Annotated[str, typer.Argument(help="The path to a YAML configuration file.")],
    debug: Annotated[bool, typer.Option(help="Enable debug logging.")] = False,
) -> None:
    """Handle the FPGA data stream in real time."""
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    stream_handler(config=Config(path))


@app.command(help="Process the ramp data.")
def process(
    *,
    path: Annotated[str, typer.Argument(help="The path to a YAML configuration file.")],
    debug: Annotated[bool, typer.Option(help="Enable debug logging.")] = False,
) -> None:
    """Process the ramp data."""
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    ramp_handler(config=Config(path))


def main() -> None:
    """The main entry point for the CLI."""
    app()
