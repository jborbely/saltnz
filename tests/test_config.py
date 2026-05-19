from saltnz.config import Config, FilterChannel, calculate_start_index

# if TYPE_CHECKING:
#     from tests.conftest import create_config


def test_calculate_start_index_filter_channel(create_config) -> None:
    config = Config(create_config())
    channel = FilterChannel(channel=1, freq=100.0, polarisation="A", range=1, repeater=1)
    calculate_start_index(channel, config)
    assert channel.start_index == 0
