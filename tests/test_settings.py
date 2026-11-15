from core.settings import DEFAULT_PIN, DEFAULTS, Settings


def test_defaults_are_valid():
    s = Settings()
    assert s.update(s.to_dict()) == []
    assert s.fallback is False


def test_valid_update_applies():
    s = Settings()
    assert s.update({"on_pm": 80, "off_pm": 40}) == []
    assert (s.on_pm, s.off_pm) == (80, 40)


def test_rejects_out_of_range_and_wrong_type():
    s = Settings()
    assert s.update({"on_pm": 5})
    assert s.update({"on_pm": "60"})
    assert s.update({"on_pm": True})
    assert s.update({"on_pm": float("nan")})
    assert s.update({"on_pm": 60.5})
    assert s.on_pm == DEFAULTS["on_pm"]


def test_cross_checks():
    s = Settings()
    assert s.update({"off_pm": 70})                       # off must be below on
    assert s.update({"med_pm": 50})                       # med at least on
    assert s.update({"high_pm": 80})                      # high above med
    assert s.update({"on_pm": 100, "off_pm": 40, "med_pm": 120, "high_pm": 200}) == []


def test_update_is_all_or_nothing():
    s = Settings()
    errs = s.update({"on_pm": 80, "rest_s": 1})
    assert errs and s.on_pm == DEFAULTS["on_pm"]


def test_unknown_key_rejected():
    assert Settings().update({"bogus": 1})


def test_choice_and_pin_validation():
    s = Settings()
    assert s.update({"aqi_scale": "epa"}) == [] and s.aqi_scale == "epa"
    assert s.update({"aqi_scale": "nope"})
    assert s.update({"pin": "12"}) and s.update({"pin": "abcd"}) and s.update({"pin": 1234})
    assert s.update({"pin": "4821"}) == [] and s.pin == "4821"


def test_public_hides_pin():
    assert "pin" not in Settings().public()


def test_bad_saved_data_falls_back_to_defaults():
    s = Settings({"on_pm": 9999})
    assert s.fallback is True and s.on_pm == DEFAULTS["on_pm"] and s.pin == DEFAULT_PIN
    assert Settings("garbage").fallback is True


def test_saved_data_loads_and_ignores_unknown_keys():
    s = Settings({"on_pm": 80, "future_option": 1})
    assert s.on_pm == 80 and s.fallback is False


def test_reset_can_keep_pin():
    s = Settings()
    s.update({"pin": "9999", "on_pm": 80})
    s.reset(keep_pin=True)
    assert s.pin == "9999" and s.on_pm == DEFAULTS["on_pm"]
