"""Plotting script for visualizing FPGA data."""  # noqa: INP001

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"

data = np.load(SAMPLES_DIR / "260324_RFSoC_raw.npy", mmap_mode="r")

plt.plot(data[:500_000, 0], "o")
plt.show()
