from datetime import datetime, timedelta, timezone

import pytest

from app.dynamic import DynamicEngine, absolute_humidity
from app.models import EntityState
from app.db import Store
from test_engine import populated, IDS, state


def setup(co2=650, outdoor_pm25=20):
    now = datetime.now(timezone.utc)
    clock = [now]
    engine = DynamicEngine(IDS, clock=lambda: clock[0])
    for s in populated(co2=co2, outdoor_pm25=outdoor_pm25).states.values():
        engine.update(s, initial=True)
    return engine, clock


def evaluate(engine, clock, minutes=0, co2=None, pm=None):
    clock[0] += timedelta(minutes=minutes)
    for key in ('co2', 'indoor_pm25', 'weather', 'indoor_temperature', 'indoor_humidity'):
        engine.states[key].last_updated = clock[0]
    if co2 is not None:
        engine.states['co2'].state = str(co2)
    if pm is not None:
        engine.states['indoor_pm25'].state = str(pm)
    return engine.recommend(engine.build_context(clock[0]))


@pytest.mark.parametrize('co2', [450, 499, 500, 550, 600, 650, 700])
def test_manual_minimum_and_low_session_target(co2):
    e, t = setup(co2)
    e.update(state('fan.air', 'on'))
    r = evaluate(e, t, co2=490)
    assert r.target_co2 == 600
    assert r.start_co2 > r.target_co2
    assert r.action != 'air_off'
    r = evaluate(e, t, minutes=9)
    assert r.action != 'air_off'
    r = evaluate(e, t, minutes=1)
    assert r.action == 'air_off'


@pytest.mark.parametrize('pmout,temp,target,pmtarget', [(10,28,650,15),(20,28,650,21),(36,28,700,21),(20,45,800,21)])
def test_normal_dynamic_targets(pmout,temp,target,pmtarget):
    e,t = setup(950,pmout)
    e.states['weather'].attributes['temperature'] = temp
    r = evaluate(e,t)
    assert (r.target_co2,r.target_pm25) == (target,pmtarget)


def test_manual_off_clears_run_timer_and_is_anchored():
    e,t = setup()
    e.update(state('fan.air','on'))
    e.update(state('fan.air','off'))
    initial = e.manual.lockout_until
    assert e.manual.minimum_run_until is None
    evaluate(e,t,minutes=5)
    assert e.manual.lockout_until == initial
    assert evaluate(e,t,co2=950).action == 'no_action'


def test_emergency_requires_ten_minutes():
    e,t = setup()
    e.update(state('fan.air','on')); e.update(state('fan.air','off'))
    assert evaluate(e,t,co2=1500).action == 'no_action'
    assert evaluate(e,t,minutes=9).action == 'no_action'
    assert evaluate(e,t,minutes=1).action == 'air_normal'


def test_flow_hold_expires_without_blocking_stop():
    e,t = setup(950)
    e.update(state('fan.air','on'))
    e.update(state('select.flow',300,context={'user_id':'person'}))
    e.handle_setting_transition('flow',100,300,'human_ha')
    r = evaluate(e,t,minutes=15,co2=600)
    assert r.flow_hold_until
    assert evaluate(e,t,minutes=2).action == 'air_off'
    assert evaluate(e,t,minutes=14).flow_hold_until is None


def test_initial_reconnect_and_unavailable_are_not_manual():
    e,t=setup()
    assert e.update(state('fan.air','on'), initial=True) is None
    assert e.runtime['session_id'] is None
    assert e.update(state('fan.air','unavailable')) is None
    assert e.update(state('fan.air','off')) is None
    assert e.runtime['session_id'] is None


def test_unknown_parent_is_not_automation():
    e,t=setup()
    assert e.classify_actor(state('fan.air','on',context={'parent_id':'random'})) == 'manual_assumed'
    e.known_contexts['known'] = t[0] + timedelta(minutes=2)
    assert e.classify_actor(state('fan.air','on',context={'parent_id':'known'})) == 'ha_automation'


def test_automation_context_survives_stop_dwell_and_device_poll():
    e, t = setup()
    e.known_contexts['stop-trigger'] = t[0] + timedelta(minutes=5)
    t[0] += timedelta(minutes=2, seconds=15)
    assert e.classify_actor(
        state('fan.air', 'off', context={'parent_id': 'stop-trigger'})
    ) == 'ha_automation'


def test_optional_weather_failure_keeps_baseline_target():
    e,t=setup(950)
    e.states['weather'].last_updated -= timedelta(hours=3)
    c=e.build_context(t[0]); r=e.recommend(c)
    assert c.values['outdoor_pm25'] is None
    assert r.target_co2 == 700 and r.input_quality == 'degraded'
    assert r.action != 'no_action'


@pytest.mark.parametrize('invalid',['nan','inf','unavailable'])
def test_invalid_critical_data_prevents_actions(invalid):
    e,t=setup()
    e.states['co2'].state=invalid
    assert evaluate(e,t).action == 'no_action'


def test_missing_trend_is_not_a_fake_estimate():
    e,t=setup(950)
    e.update(state('fan.air','on'))
    assert evaluate(e,t).estimated_remaining_minutes is None


def test_absolute_humidity_uses_temperature():
    assert absolute_humidity(30,50) > absolute_humidity(10,50)
    assert absolute_humidity(25,None) is None


def test_restart_restores_session_not_continuity():
    e,t=setup()
    e.update(state('fan.air','on'))
    evaluate(e,t,co2=1500)
    restored=DynamicEngine(IDS)
    restored.restore(e.runtime)
    assert restored.runtime['session_id'] == e.runtime['session_id']
    assert restored.runtime['high_since'] is None


def test_decision_audit_export_and_retention(tmp_path):
    store=Store(str(tmp_path/'audit.db'))
    e,t=setup(); r=evaluate(e,t)
    p=r.json_dict(); p['updated_at']=t[0].isoformat()
    store.decision(p,e.build_context(t[0]).values)
    exported=list(store.export())
    assert exported[0]['target_co2'] == 650
    assert exported[0]['execution_status'] == 'not_executed'
    assert exported[0]['inputs']['co2'] == 650
    with pytest.raises(Exception):
        store.decision(p,{})
    store.db.rollback()
    store.cleanup(t[0]+timedelta(days=91))
    assert list(store.export()) == []


def test_active_session_survives_retention(tmp_path):
    store=Store(str(tmp_path/'audit.db'))
    e,t=setup(); e.update(state('fan.air','on'))
    r=evaluate(e,t); p=r.json_dict(); p['updated_at']=t[0].isoformat()
    store.decision(p,{})
    store.cleanup(t[0]+timedelta(days=91), r.session_id)
    assert len(list(store.export(session_id=r.session_id))) == 1


def test_stale_breaks_continuous_high_evidence():
    e,t=setup(1500)
    evaluate(e,t)
    e.states['co2'].state='unavailable'
    evaluate(e,t,minutes=9)
    assert not e.runtime['high_since']
    evaluate(e,t,minutes=1,co2=1500)
    assert not e.runtime['emergency']


def test_equal_value_recent_report_is_fresh():
    e,t=setup(950)
    e.states['co2'].last_updated=t[0]-timedelta(hours=1)
    e.states['co2'].last_reported=t[0]
    c=e.build_context(t[0])
    assert c.values['co2']==950 and 'co2' not in c.stale


def test_temperature_forecast_correction_is_bounded():
    e,t=setup(950)
    c=e.build_context(t[0]); base=e.lockout_minutes(c)
    c.values['outdoor_temperature']=-10
    c.values['forecast']={'hours':{'1':{'temperature':-15}}}
    adjusted=e.lockout_minutes(c)
    assert adjusted<=base*1.2


def test_clean_outdoor_prefers_maximum_flow():
    e,t=setup(950,10)
    e.states['weather'].attributes['aqi']['pm10']=40
    r=evaluate(e,t)
    assert r.flow == 300
    assert '最大风量300' in r.reason


def test_polluted_outdoor_keeps_flow_cap():
    e,t=setup(950,49)
    e.states['weather'].attributes['aqi']['aqi']=120
    r=evaluate(e,t)
    assert r.flow <= 140
    assert '最大风量300' not in r.reason


@pytest.mark.parametrize('co2,pm,action', [(901,20,'air_normal'),(800,27,'air_normal'),(800,26,'no_action')])
def test_ordinary_weather_legacy_start_floor(co2, pm, action):
    e,t = setup(co2,20)
    e.states['weather'].attributes['temperature'] = 35
    r = evaluate(e,t,pm=pm)
    assert r.start_co2 <= 900 and r.start_pm25 <= 26
    assert r.target_co2 <= 700 and r.target_pm25 <= 21
    assert r.action == action


@pytest.mark.parametrize('co2,pm,stops', [(700,20,False),(699,21,False),(699,20,True)])
def test_legacy_stop_requires_both_strict_bounds(co2,pm,stops):
    e,t = setup(950,20)
    e.states['weather'].attributes['temperature'] = 35
    e.update(state('fan.air','on'))
    evaluate(e,t,co2=co2,pm=pm)
    assert (evaluate(e,t,minutes=10).action == 'air_off') == stops


@pytest.mark.parametrize('aqi', [100, 101, 104, 150, 151, 200])
def test_aqi_alone_does_not_relax_legacy_floor(aqi):
    e,t = setup(950,49)
    e.states['weather'].attributes['aqi']['aqi'] = aqi
    r = evaluate(e,t)
    assert r.target_co2 == 700
    assert r.start_co2 <= 900
    assert r.target_pm25 <= 21 and r.start_pm25 <= 26
    if aqi > 100:
        assert r.flow <= 140
        assert 'AQI本身不放宽' in r.reason
    assert 'CO₂停止目标800例外' not in r.reason


@pytest.mark.parametrize('co2,pm,stops', [(747,15,False),(724,13,False),(700,12,False),(699,21,False),(699,20,True)])
def test_aqi_104_early_stop_regression(co2,pm,stops):
    e,t = setup(950,49)
    e.states['weather'].attributes['aqi']['aqi'] = 104
    e.update(state('fan.air','on'))
    evaluate(e,t,co2=co2,pm=pm)
    r = evaluate(e,t,minutes=10)
    assert (r.action == 'air_off') == stops
    assert r.target_co2 == 700
    assert r.flow <= 140


@pytest.mark.parametrize('field,value,reason', [('temperature',45,'温差≥15℃'),('pm10',150,'PM10≥150')])
def test_explicit_weather_exceptions_retain_relaxation(field,value,reason):
    e,t = setup(950,49)
    weather = e.states['weather'].attributes
    if field == 'pm10':
        weather['aqi'][field] = value
    else:
        weather[field] = value
    r = evaluate(e,t)
    assert r.target_co2 == 800
    assert r.start_co2 == (1000 if field == 'pm10' else 950)
    assert reason in r.reason
    assert 'CO₂停止目标800例外' in r.reason
