# tests/test_webapp_auth.py
# webapp.py の認証まわりのテスト（ADR-032）
# - /login が OAuth2 state を発行してセッションに保存する
# - /callback が state 不一致・欠落を拒否する
# - /ws/hyouibana が未ログイン接続を拒否する
import os
import sys

import pytest
from quart.testing.connections import WebsocketResponseError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('SECRET_KEY', 'test-secret-key')

import webapp  # noqa: E402


@pytest.fixture
def client():
    return webapp.app.test_client()


async def test_login_issues_state_and_stores_it_in_session(client):
    res = await client.get('/login')
    assert res.status_code == 200
    async with client.session_transaction() as sess:
        state = sess['oauth_state']
    assert len(state) >= 32
    assert f'state={state}' in (await res.get_data(as_text=True))


@pytest.mark.parametrize('query', ['?code=abc', '?code=abc&state=wrong', '?code=abc&state=%E3%81%82'])
async def test_callback_rejects_missing_or_wrong_state(client, query):
    await client.get('/login')
    res = await client.get(f'/callback{query}')
    assert res.status_code == 400
    assert 'Invalid OAuth state' in (await res.get_data(as_text=True))


async def test_callback_rejects_when_login_was_not_started(client):
    # セッションに state が無い（/login を経ていない）callback は拒否する
    res = await client.get('/callback?code=abc&state=anything')
    assert res.status_code == 400


async def test_callback_state_is_single_use(client):
    await client.get('/login')
    async with client.session_transaction() as sess:
        state = sess['oauth_state']
    # 正しい state でも code が無ければ token 交換前に 400（外部 API は呼ばれない）
    first = await client.get(f'/callback?state={state}')
    assert 'No code provided' in (await first.get_data(as_text=True))
    # 同じ state の再利用は拒否される
    second = await client.get(f'/callback?code=abc&state={state}')
    assert 'Invalid OAuth state' in (await second.get_data(as_text=True))


async def test_ws_rejects_unauthenticated_connection(client):
    with pytest.raises(WebsocketResponseError) as exc:
        async with client.websocket('/ws/hyouibana') as ws:
            await ws.receive()
    assert exc.value.response.status_code == 401
