import pytest
from leaddesk_ai.services.calculations import calculate_mao


def test_mao_calculation():
    assert calculate_mao(300000, .70, 50000, 5000, 5000, 10000) == 140000


def test_percentage_input():
    assert calculate_mao(300000, 70, 50000, 5000, 5000, 10000) == 140000


def test_negative_rejected():
    with pytest.raises(ValueError): calculate_mao(300000, .7, -1, 0, 0, 0)
