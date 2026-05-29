"""Find nominal frequencies."""  # noqa: INP001

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from saltnz import Config

skip = 4
end = 100_000
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"

cfg = Config(SAMPLES_DIR / "260217_nz_bittware_config.yml")
data = np.load(SAMPLES_DIR / "260324_RFSoC_raw.npy", mmap_mode="r")

for channel in range(1):  # data.shape[1]
    out = np.array([])
    for i in range(0, end, 20):
        out = np.append(out, np.mean(data[i + skip : i + 20, channel]))
    ave = np.average(out) / 1e6
    std = np.std(out, ddof=1) / 1e6
    if ave > 0:
        print(channel, f"{std / ave:.6%}", ave, std)  # noqa: T201

plt.plot(out, "o")
plt.show()
