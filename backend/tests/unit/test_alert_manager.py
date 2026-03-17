import pytest
import respx
import httpx
from httpx import Response
from backend.worker.alert_manager import push_to_bark, push_to_serverchan, trigger_alert_endpoint, AlertPayload
from backend.models.system import SystemLog
from tests.factories import AlertPayloadFactory, MockUserFactory

@pytest.fixture
def mock_db_session(mocker):
    """Mock database session to prevent actual DB writes during testing"""
    mock_session = mocker.AsyncMock()
    return mock_session

@pytest.fixture
def mock_settings():
    """Mock app settings if needed by dependencies"""
    class Settings:
        pass
    return Settings()

@pytest.fixture
def mock_user():
    """Mock User JWT payload（法典 5.1.2：由工厂生成，无硬编码）"""
    return MockUserFactory.build()

@pytest.mark.asyncio
@respx.mock
async def test_push_to_bark_critical():
    """验证遇到 Critical 级别灾难时，是否注入了穿透参数 (Sound, TimeSensitive)"""
    bark_url = "https://api.day.app/mock_key"
    
    # Mock the Bark API endpoint to return 200 OK
    route = respx.get(f"{bark_url}/System%20Failure/Disk%20Rot%20Detected").mock(return_value=Response(200))
    
    await push_to_bark(bark_url, "System Failure", "Disk Rot Detected", "critical")
    
    # Assert
    assert route.called
    request = route.calls.last.request
    assert request.url.params["sound"] == "alarm"
    assert request.url.params["level"] == "timeSensitive"

@pytest.mark.asyncio
@respx.mock
async def test_push_to_bark_warning():
    """验证普通 Warning 是否为静默推送（不带警报音）"""
    bark_url = "https://api.day.app/mock_key"
    route = respx.get(f"{bark_url}/High%20Load/CPU%20is%20hot").mock(return_value=Response(200))
    
    await push_to_bark(bark_url, "High Load", "CPU is hot", "warning")
    
    assert route.called
    request = route.calls.last.request
    assert "sound" not in request.url.params
    assert "level" not in request.url.params

@pytest.mark.asyncio
@respx.mock
async def test_alert_manager_info_no_push(mock_db_session, mock_settings, mock_user, mocker):
    """验证信息级 (Info) 仅做内网写库日志，绝对不发起外部网络请求骚扰用户"""
    payload = AlertPayloadFactory.build(level="info", title="User Login", message="Admin logged in")
    
    # Patch async gathers/pushes just in case
    mock_bark = mocker.patch("backend.worker.alert_manager.push_to_bark")
    mock_sc = mocker.patch("backend.worker.alert_manager.push_to_serverchan")

    res = await trigger_alert_endpoint(payload, mock_settings, mock_db_session, mock_user)
    
    assert res["status"] == "logged"
    assert "channels" not in res
    
    # Assert purely database commit happened
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    
    added_obj = mock_db_session.add.call_args[0][0]
    assert isinstance(added_obj, SystemLog)
    assert added_obj.action == "ALERT_INFO"
    
    # MUST NOT push
    mock_bark.assert_not_called()
    mock_sc.assert_not_called()

@pytest.mark.asyncio
@respx.mock
async def test_alert_manager_critical_dispatch(mock_db_session, mock_settings, mock_user, mocker, monkeypatch):
    """验证高危事件并行触发 Bark 和 Server酱"""
    payload = AlertPayloadFactory.build(level="critical", title="POWER LOSS", message="UPS dying")
    
    monkeypatch.setenv("BARK_URL", "http://bark.dev/key")
    monkeypatch.setenv("SERVER_CHAN_KEY", "SCT_xxx")
    
    mock_bark = mocker.patch("backend.worker.alert_manager.push_to_bark", return_value=None)
    mock_sc = mocker.patch("backend.worker.alert_manager.push_to_serverchan", return_value=None)

    res = await trigger_alert_endpoint(payload, mock_settings, mock_db_session, mock_user)
    
    # In asyncio.create_task(asyncio.wait(tasks)), execution depends on loop timing in test. 
    # But we can verify it returned dispatched properly
    assert res["status"] == "alert_dispatched"
    assert res["channels"] == 2
    
    mock_db_session.add.assert_called_once()
    
    # We yield control slightly to allow the fire-and-forget task to spin
    import asyncio
    await asyncio.sleep(0.01)
    
    mock_bark.assert_called_once_with("http://bark.dev/key", "POWER LOSS", "UPS dying", "critical")
    mock_sc.assert_called_once_with("SCT_xxx", "POWER LOSS", "UPS dying")
