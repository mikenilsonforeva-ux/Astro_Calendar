import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402


@pytest.fixture(scope="session")
def ctx():
    """Контекст расчётов для Москвы; тест пропускается, если нет Skyfield или эфемерид."""
    pytest.importorskip("skyfield")
    path = config.find_ephemeris_file()
    if path is None:
        pytest.skip("Нет файла эфемерид (resources/ephemeris/de440s.bsp)")
    from astronomy.context import AstroContext
    return AstroContext.create(55.7558, 37.6173, 150, "Europe/Moscow", path, "Москва")
