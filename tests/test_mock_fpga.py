import pytest

from saltnz.mock_fpga import indices


def test_indices_start_equals_stop() -> None:
    with pytest.raises(ValueError, match=r"start \(0\) must be less than stop \(0\)"):
        _ = next(indices(stop=0))


def test_indices_restart_equals_stop() -> None:
    with pytest.raises(ValueError, match=r"restart \(2\) must be less than stop \(2\)"):
        _ = next(indices(stop=2, restart=2))


def test_indices_start_0_restart_none() -> None:
    generator = indices(stop=3)
    assert next(generator) == 0
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 0
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 0
    assert next(generator) == 1


def test_indices_start_1_restart_none() -> None:
    generator = indices(stop=3, start=1)
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 1


def test_indices_start_1_restart_0() -> None:
    generator = indices(stop=3, start=1, restart=0)
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 0
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 0
    assert next(generator) == 1
