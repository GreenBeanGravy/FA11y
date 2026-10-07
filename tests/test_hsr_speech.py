from lib.detection.hsr import health_shield_text, _READ_ERROR


def test_short_speech_says_only_the_numbers():
    assert health_shield_text(100, 50, short=True) == "100, 50"
    assert health_shield_text(87, None, short=True) == "87, 0"
    assert health_shield_text(100, 50, short=False) == "100 Health, 50 Shield"
    assert health_shield_text(100, None, short=False) == "100 Health, No Shield"
    assert health_shield_text(None, 50, short=True) == "Cannot find Health Value!"
    assert health_shield_text(_READ_ERROR, None, short=False) == "Error reading Health bar."
