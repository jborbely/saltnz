"""Plotting script for visualizing FPGA data."""  # noqa: INP001

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"

data = np.load(SAMPLES_DIR / "260324_RFSoC_raw.npy", mmap_mode="r")

channel = 79
plt.plot(data[1_680_000:1_900_000:100, channel], "-")
plt.title(f"Channel {channel}")
plt.xlabel("Sample")
plt.ylabel("Frequency (Hz)")
plt.show()
