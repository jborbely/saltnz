# saltnz

Real-time FPGA stream handling tools for the NZ measurement setup.

`saltnz` receives frequency data from an FPGA over ZeroMQ, groups samples into ramp-sized arrays, and publishes both raw ramp data and per-channel averaged data for downstream consumers. It also includes a mock FPGA streamer for replaying recorded `.npy` data during development, testing, and demonstrations.

## Features

- Load SALT measurement configuration from YAML.
- Handle FPGA sample streams in real time.
- Build complete ramp arrays from trigger-marked FPGA rows.
- Average filtered and summed channels after each channel's configured discard period.
- Replay recorded FPGA data from NumPy files.
- Provide a `salt` command-line interface for running the mock stream, ramp handler, and averaging process.

## Installation

This project uses `uv`.

```powershell
uv sync
```

The package requires Python 3.14 or newer.

## Command Line Usage

The package installs a CLI named `salt`.

### What each component does

- `mock` / `mock_fpga`: implemented in `src/saltnz/mock_fpga.py`. It replays recorded `.npy` rows and publishes them over ZeroMQ as if they were real FPGA output. It also inserts the trigger field into each row so the downstream handler can detect ramp boundaries.
- `handler` / `handle_fpga`: implemented in `src/saltnz/handle_fpga.py`. It receives FPGA rows on port `5555`, detects the ramp-start trigger, builds each ramp into a complete 2D array, and republishes the ramp arrays on port `5556`.
- `process` / `ramp_handler`: also implemented in `src/saltnz/handle_fpga.py`. It subscribes to ramp arrays from port `5556`, discards the configured number of initial samples per channel, averages the remaining data for each channel, and publishes the averaged channel results on port `5557`.

### System data flow

```text
mock_fpga / FPGA source
    |
    | tcp://127.0.0.1:5555
    v
salt handler (builds ramps)
    |
    | tcp://127.0.0.1:5556
    v
salt process (averages channels)
    |
    | tcp://127.0.0.1:5557
    v
downstream consumer
```

### Run the FPGA stream handler

Receives FPGA samples on port `5555`, groups them into ramps, and publishes ramp arrays on port `5556`.

```powershell
uv run salt handler .\samples\260217_nz_bittware_config.yml --debug
```

### Run the ramp processor

Subscribes to ramp arrays on port `5556`, computes per-channel averages, and publishes averaged data on port `5557`.

```powershell
uv run salt process .\samples\260217_nz_bittware_config.yml --debug
```

### Run the mock FPGA streamer

Replays rows from a NumPy `.npy` file and publishes them as if they came from the FPGA.

For the mock setup to run, place both the recorded `.npy` data file and the matching YAML configuration file in the `samples/` folder.

```powershell
uv run salt mock .\samples\260324_RFSoC_raw.npy .\samples\260217_nz_bittware_config.yml --debug
```

Optional arguments:

```powershell
uv run salt mock DATA.npy CONFIG.yml --start 0 --stop 50000 --restart 0 --debug
```

## Simulating a V1 Stream

For local development, the included batch file starts the three required processes:

```powershell
.\simulate_v1.bat
```

This launches:

1. the mock FPGA data source,
2. the FPGA stream handler,
3. the averaged ramp processor.

## Configuration

Configuration is loaded from a YAML file. The currently implemented measurement type is `V1` (NZ setup).

The handler uses:

- `measurement_type`
- `ramp_time_ms`
- `sampling_time_ms`
- `filter_channels`
- `sum_channels`

Each filter channel includes the channel number, frequency, polarisation, range, and repeater. For V1 measurements, `saltnz` calculates the first good sample index for each channel and discards earlier samples when computing averages.

## Development

Run the test suite with:

```powershell
uv run pytest
```

Run linting with:

```powershell
uv run ruff check
```

The `scripts/` directory contains exploratory plotting and simulation scripts for visualising ramp behaviour and FPGA output.

## Notes

- `V1` measurements are implemented.
- `V2` configuration loading is recognised but not yet implemented.
- The default ZeroMQ ports are defined in `src/saltnz/constants.py`.
