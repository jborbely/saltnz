"""Constants for SaltNZ."""

import logging

FPGA_PORT = 5555
MSL_RAMP_PORT = 5556
MSL_AVERAGED_PORT = 5557

FPGA_INTERCEPT_MHZ = 2.046338
"""Calculated from a linear fit to the beat note vs round-trip time from a repeater.

Not zero because two AOM in series have an RF drive that is 2 MHz different.
"""

SWEEP_RATE_MHZ_PER_MS = 1.260
DISCARD_MARGIN_SAMPLES = 0.1
WRAPPED_RANGE_OFFSET_MHZ = 25

logger = logging.getLogger(__name__)
