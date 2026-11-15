from core.settings import HARD_MAX_MANUAL_S
from helpers import make_ctl, run_ctl


def test_hysteresis():
    ctl, v, bank, _ = make_ctl()
    v["b"] = 50                         # between 35 and 60: stays off
    t = run_ctl(ctl, v, 0, 120)
    assert ctl.state == "IDLE"
    v["b"] = 100
    t = run_ctl(ctl, v, t, 120)
    assert ctl.state == "RUNNING" and bank.speed > 0
    v["b"] = 50                         # still above 35: keeps running
    t = run_ctl(ctl, v, t, 120)
    assert ctl.state == "RUNNING"
    v["b"] = 30
    run_ctl(ctl, v, t, 120)
    assert ctl.state == "IDLE" and bank.speed == 0


def test_run_limit_rest_and_restart():
    ctl, v, bank, _ = make_ctl()
    v["b"] = 100
    t = run_ctl(ctl, v, 0, 3600 + 120)
    assert ctl.state == "REST" and bank.speed == 0
    t = run_ctl(ctl, v, t, 1700)
    assert ctl.state == "REST"
    run_ctl(ctl, v, t, 200)
    assert ctl.state == "RUNNING"


def test_speed_follows_pollution_but_not_too_fast():
    ctl, v, bank, _ = make_ctl()
    v["b"] = 70
    t = run_ctl(ctl, v, 0, 120)
    assert bank.speed == 1
    v["b"] = 200
    t = run_ctl(ctl, v, t, 300)
    assert bank.speed == 3
    switches = bank.switches
    v["b"] = 100                        # would be speed 2, but only after the 60 s hold
    run_ctl(ctl, v, t, 300)
    assert bank.speed == 2 and bank.switches == switches + 1


def test_manual_overrides_auto_and_auto_resumes():
    ctl, v, bank, _ = make_ctl()
    t = run_ctl(ctl, v, 0, 60)
    ctl.command("speed:3", t)
    t = run_ctl(ctl, v, t, 300)
    assert bank.speed == 3 and ctl.state == "MANUAL"
    ctl.command("auto", t)
    run_ctl(ctl, v, t, 60)
    assert bank.speed == 0 and ctl.mode == "AUTO"


def test_up_down_off_and_bad_input():
    ctl, v, bank, _ = make_ctl()
    ctl.command("up", 0)
    ctl.command("up", 1)
    assert bank.speed == 2
    ctl.command("down", 2)
    assert bank.speed == 1
    ctl.command("off", 3)
    assert bank.speed == 0 and ctl.mode == "MANUAL"
    for bad in ("speed:4", "explode", "speed:x"):
        try:
            ctl.command(bad, 4)
            raise AssertionError("expected ValueError for " + bad)
        except ValueError:
            pass


def test_restart_restores_manual_speed():
    ctl, v, bank, _ = make_ctl()
    ctl.command("speed:2", 0)
    saved = ctl.snapshot()
    ctl2, v2, bank2, _ = make_ctl()
    ctl2.restore(saved, 100)
    assert bank2.speed == 2 and ctl2.mode == "MANUAL" and ctl2.state == "MANUAL"


def test_restart_in_auto_stays_off_until_readings_say_otherwise():
    ctl, v, bank, _ = make_ctl()
    ctl2, _, bank2, _ = make_ctl()
    ctl2.restore(ctl.snapshot(), 0)
    assert bank2.speed == 0 and ctl2.mode == "AUTO"


def test_restore_ignores_garbage():
    ctl, _, bank, _ = make_ctl()
    ctl.restore({"mode": "MANUAL", "manual_speed": 9, "total_run_s": 50}, 0)
    assert bank.speed == 0 and ctl.mode == "AUTO" and ctl.total_run_s == 50


def test_manual_run_has_a_hard_limit():
    ctl, v, bank, events = make_ctl()
    ctl.command("speed:3", 0)
    run_ctl(ctl, v, 0, HARD_MAX_MANUAL_S + 20)
    assert bank.speed == 0 and ctl.mode == "AUTO" and ctl.state == "REST"
    assert any("Manual run limit" in m for _, m in events)


def test_sensor_loss_fails_safe_and_recovers():
    ctl, v, bank, events = make_ctl()
    v["b"] = 100
    t = run_ctl(ctl, v, 0, 120)
    assert bank.speed > 0
    v["b"] = None
    t = run_ctl(ctl, v, t, 60)
    assert ctl.fault and bank.speed == 0
    v["b"] = 100
    run_ctl(ctl, v, t, 120)
    assert not ctl.fault and bank.speed > 0


def test_manual_keeps_running_without_sensor():
    ctl, v, bank, _ = make_ctl()
    ctl.command("speed:2", 0)
    v["b"] = None
    run_ctl(ctl, v, 0, 120)
    assert bank.speed == 2


def test_clogged_filter_alerts_once_and_reset_clears_it():
    ctl, v, bank, events = make_ctl()
    v["b"], v["a"] = 100, 80            # 20% efficient
    t = run_ctl(ctl, v, 0, 2500)
    alerts = [m for level, m in events if level == "alert"]
    assert len(alerts) == 1 and "replace the filter" in alerts[0]
    ctl.filter_replaced(t)
    assert ctl.total_run_s == 0 and not ctl.filter.alerted


def test_healthy_filter_no_alert():
    ctl, v, bank, events = make_ctl()
    v["b"], v["a"] = 100, 10
    run_ctl(ctl, v, 0, 2500)
    assert not [1 for level, _ in events if level == "alert"]


def test_run_hours_reminder():
    ctl, v, bank, events = make_ctl(filter_hours=10)
    ctl.total_run_s = 10 * 3600 - 30        # nearly at the limit (restored after a restart)
    ctl.command("speed:1", 0)
    run_ctl(ctl, v, 0, 120)
    reminders = [m for _, m in events if "run hours" in m]
    assert len(reminders) == 1 and ctl.hours_alerted
