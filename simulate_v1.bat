@echo off
start uv run python scripts\dashboard.py .\samples\260217_nz_bittware_config.yml
start salt process .\samples\260217_nz_bittware_config.yml --debug
start salt handler .\samples\260217_nz_bittware_config.yml --debug
start salt mock .\samples\260324_RFSoC_raw.npy .\samples\260217_nz_bittware_config.yml --start 1680000 --debug