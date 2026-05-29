"""Constants for SaltNZ."""

import logging

FPGA_PORT = 5555
MSL_RAMP_PORT = 5556
MSL_AVERAGED_PORT = 5557

FPGA_INTERCEPT_HZ = 2.046338e6
"""Calculated from a linear fit to the beat note vs round-trip time from a repeater.

Not zero because two AOMs in series have a RF drive difference of 2 MHz.
"""

SWEEP_RATE_HZ_PER_S = 1.260e9
DISCARD_MARGIN_SAMPLES = 0.1
WRAPPED_RANGE_OFFSET_HZ = 25e6

logger = logging.getLogger(__name__)
