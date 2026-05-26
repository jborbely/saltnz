"""Plotting script for visualizing FPGA data."""  # noqa: INP001

import matplotlib.pyplot as plt
import numpy as np

data = np.load(r".\samples\260324_RFSoC_raw_first_50000_rows.npy", mmap_mode="r")

plt.plot(data[:40, 25], "o")
plt.show()
