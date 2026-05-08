"""Simulate the ramp and the returned light from a repeater."""  # noqa: INP001

from itertools import pairwise

import matplotlib.pyplot as plt
import numpy as np

type Array1D = np.ndarray[tuple[int], np.dtype[np.float64]]

ramp_slope = 1.257e9  # Hz/s
ramp_duration = 0.2  # s
dt = 1e-6  # approximate sampling time, s
repeater_distance = 3843.757e3  # m
sample_interval = 0.01  # s
c = 299792458.0  # speed of light in vacuum, m/s
n = 1.4682  # index of refraction
wl = 1567.13e-9  # wavelength, m
cycles = 5  # number of ramp cycles to plot
laser_frequency = 0  # c / wl  # Hz


def simulate(distance: float) -> tuple[float, float, Array1D, Array1D]:
    """Simulate a ramp.

    Args:
        distance: The distance to a repeater, in metres.

    Returns:
        (round-trip delay, actual dt, time array, ramp array in MHz)
    """
    delay = (2.0 * distance) / (c / n)  # round-trip delay for the light to return from a repeater

    x, dx = np.linspace(0, (ramp_duration * cycles) + delay, num=round((ramp_duration * cycles) / dt), retstep=True)
    y = np.array([])
    for i in range(cycles):
        x0 = i * ramp_duration
        ramp_x = x[(x >= x0) & (x <= x0 + ramp_duration)]
        y = np.append(y, ramp_slope * (ramp_x - x0) + laser_frequency)

    return delay, dx, x, np.append(y, np.full((x.size - y.size,), laser_frequency)) * 1e-6  # in MHz

# the ramp signal at Auckland (the light that did not go to a sub-sea cable)
delay, dx, x, auckland = simulate(repeater_distance)

# the signal from the repeater
repeater = np.roll(auckland, shift=round(delay / dx))

# the beat frequency
beat = np.abs(repeater - auckland)

# the data that the FPGA outputs
intervals = sample_interval * np.arange(round(x[-1] / sample_interval) + 1)
fpga = np.array([np.average(beat[(x >= i) & (x <= j)]) for i, j in pairwise(intervals)])

fig, (ax1, ax3) = plt.subplots(2, 1)

ax1.set_xlabel("time [s]")
ax1.set_ylabel("Ramp [MHz]")
ax1.plot(x, auckland, color="tab:blue")
ax1.plot(x, repeater, color="tab:red")
ax1.set_title(f"Round-trip delay {delay * 1e3:.1f} ms")

ax2 = ax1.twinx()  # instantiate a second Axes that shares the same x-axis

ax2.set_ylabel("Beat [MHz]", color="tab:green")
ax2.plot(x, beat, color="tab:green")
ax2.tick_params(axis="y", labelcolor="tab:green")

ax3.set_xlabel("time [s]")
ax3.set_ylabel("FPGA output [MHz]")
ax3.plot(intervals[1:], fpga, "-o", color="black")

fig.tight_layout()
plt.show()
