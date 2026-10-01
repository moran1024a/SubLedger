from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.api import notifications as api
from app.api.dependencies import get_current_user
from app.models import NotificationSetting, User
from app.security import decrypt_secret
from app.services.notification_verification import NotificationVerification
from app.services.notifications import DeliveryError
from test_notification_security import notification_client  # noqa: F401

ROOT = '/api/v1/me/notification-settings'
EMAIL = dict(email_enabled=True, smtp_host='smtp.example.com', smtp_port=465, smtp_security='ssl',
             sender_email='sender@example.com', recipient_email='receiver@example.com', smtp_password='draft-secret')
FEISHU = dict(feishu_enabled=True, feishu_webhook='https://open.feishu.cn/open-apis/bot/v2/hook/test-token')


@pytest.fixture
def setup(notification_client, monkeypatch):
    client, factory, app = notification_client
    app.state.notification_verification = NotificationVerification()
    app.state.notification_verification.cooldown = 0
    monkeypatch.setattr(api, 'resolve_smtp_target', lambda *a, **k: ('smtp.example.com', []))
    monkeypatch.setattr(api, 'send_test_email', lambda *a: None)
    monkeypatch.setattr(api, 'send_test_feishu', lambda *a: None)
    return client, factory, app


def test_draft_test_is_not_a_save_and_proof_matches_secrets(setup):
    client, factory, app = setup
    payload = dict(EMAIL, settings_version=client.get(ROOT).json()['settings_version'])
    response = client.put(ROOT, json=payload)
    assert response.status_code == 400 and response.json()['code'] == 'NOTIFICATION_TEST_REQUIRED'
    tested = client.post(ROOT + '/test-email', json=payload)
    assert tested.status_code == 200
    assert 'draft-secret' not in tested.text
    with factory() as db:
        assert db.get(NotificationSetting, 1).smtp_host is None
    token = tested.json()['verification_token']
    altered = dict(payload, smtp_password='different-secret', email_verification_token=token)
    assert client.put(ROOT, json=altered).json()['code'] == 'NOTIFICATION_TEST_REQUIRED'
    saved = client.put(ROOT, json=dict(payload, email_verification_token=token))
    assert saved.status_code == 200
    assert 'draft-secret' not in saved.text
    with factory() as db:
        assert decrypt_secret(app.state.fernet, db.get(NotificationSetting, 1).smtp_password_encrypted) == 'draft-secret'
    assert not app.state.notification_verification._grants


def test_channel_proofs_are_independent_and_both_required(setup):
    client, _, _ = setup
    both = dict(EMAIL, **FEISHU)
    # An incomplete unrelated draft must not prevent testing the selected channel.
    email = client.post(ROOT + '/test-email', json=dict(EMAIL, feishu_enabled=True))
    assert email.status_code == 200
    both['email_verification_token'] = email.json()['verification_token']
    assert client.put(ROOT, json=both).json()['code'] == 'NOTIFICATION_TEST_REQUIRED'
    feishu = client.post(ROOT + '/test-feishu', json=dict(FEISHU, email_enabled=True))
    assert feishu.status_code == 200
    both['feishu_verification_token'] = feishu.json()['verification_token']
    assert client.put(ROOT, json=both).status_code == 200


def test_expired_cross_session_and_restarted_proofs_are_rejected(setup):
    client, _, app = setup
    client.cookies.set('session', 'session-a')
    tested = client.post(ROOT + '/test-email', json=EMAIL).json()
    payload = dict(EMAIL, email_verification_token=tested['verification_token'])
    client.cookies.set('session', 'session-b')
    assert client.put(ROOT, json=payload).json()['code'] == 'NOTIFICATION_TEST_REQUIRED'
    client.cookies.set('session', 'session-a')
    store = app.state.notification_verification
    entry = store._grants[(1, 'email')]
    store._grants[(1, 'email')] = (*entry[:-1], 0)
    assert client.put(ROOT, json=payload).json()['code'] == 'NOTIFICATION_TEST_REQUIRED'
    app.state.notification_verification = NotificationVerification()
    assert client.put(ROOT, json=payload).json()['code'] == 'NOTIFICATION_TEST_REQUIRED'


def test_cross_account_proof_is_rejected(setup):
    client, factory, app = setup
    token = client.post(ROOT + '/test-feishu', json=FEISHU).json()['verification_token']
    with factory() as db:
        old = db.get(User, 1)
        db.add(User(id=2, username='second', password_hash='hash', role='user', is_active=True, timezone='UTC', currency_code='CNY', created_at=old.created_at, updated_at=old.updated_at))
        setting = db.get(NotificationSetting, 1)
        db.add(NotificationSetting(user_id=2, advance_time=setting.advance_time, same_day_time=setting.same_day_time, updated_at=setting.updated_at))
        db.commit()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2)
    assert client.put(ROOT, json=dict(FEISHU, feishu_verification_token=token)).json()['code'] == 'NOTIFICATION_TEST_REQUIRED'


@pytest.mark.parametrize('failure', [DeliveryError('SMTP_REJECTED'), DeliveryError('DELIVERY_UNKNOWN', unknown=True), TimeoutError()])
def test_failed_or_unknown_test_never_grants_save(setup, monkeypatch, failure):
    client, factory, app = setup
    def fail(*args): raise failure
    monkeypatch.setattr(api, 'send_test_email', fail)
    result = client.post(ROOT + '/test-email', json=EMAIL)
    assert result.status_code == 400
    assert 'verification_token' not in result.json()
    assert not app.state.notification_verification._grants
    with factory() as db:
        assert not db.get(NotificationSetting, 1).email_enabled


def test_configuration_change_during_test_invalidates_result_without_overwriting(setup, monkeypatch):
    client, factory, _ = setup
    def change(*args):
        with factory() as db:
            setting = db.get(NotificationSetting, 1)
            setting.advance_days = 8
            setting.updated_at += timedelta(seconds=1)
            db.commit()
    monkeypatch.setattr(api, 'send_test_email', change)
    assert client.post(ROOT + '/test-email', json=EMAIL).status_code == 409
    with factory() as db:
        setting = db.get(NotificationSetting, 1)
        assert setting.advance_days == 8 and setting.smtp_host is None


def test_save_detects_configuration_change_and_unchanged_credentials_need_no_test(setup, monkeypatch):
    client, factory, _ = setup
    token = client.post(ROOT + '/test-email', json=EMAIL).json()['verification_token']
    saved = client.put(ROOT, json=dict(EMAIL, email_verification_token=token)).json()
    def no_dns(*args, **kwargs): raise AssertionError('Reminder edits must not need network access')
    monkeypatch.setattr(api, 'resolve_smtp_target', no_dns)
    changed = client.put(ROOT, json={'advance_days': 5, 'settings_version': saved['settings_version']})
    assert changed.status_code == 200
    assert client.put(ROOT, json={'advance_days': 6, 'settings_version': saved['settings_version']}).status_code == 409
    assert client.put(ROOT, json={'email_enabled': False}).status_code == 200
    monkeypatch.setattr(api, 'resolve_smtp_target', lambda *a, **k: ('smtp.example.com', []))
    assert client.put(ROOT, json={'email_enabled': True}).json()['code'] == 'NOTIFICATION_TEST_REQUIRED'
    # Omitted secret is merged from stored credentials before testing.
    draft = dict(EMAIL); draft.pop('smtp_password')
    tested = client.post(ROOT + '/test-email', json=draft)
    assert client.put(ROOT, json=dict(draft, email_verification_token=tested.json()['verification_token'])).status_code == 200


def test_test_rate_limit_and_inflight_limit(setup):
    client, _, app = setup
    store = app.state.notification_verification
    store.cooldown = 30
    assert client.post(ROOT + '/test-feishu', json=FEISHU).status_code == 200
    assert client.post(ROOT + '/test-feishu', json=FEISHU).status_code == 429
    store.cooldown = 0
    store.start(2, 'email')
    try:
        with pytest.raises(Exception) as error:
            store.start(2, 'email')
        assert error.value.code == 'NOTIFICATION_TEST_RATE_LIMITED'
    finally:
        store.finish(2, 'email')


def test_real_local_smtp_draft_then_save(notification_client):
    from socketserver import StreamRequestHandler, ThreadingTCPServer
    from threading import Thread
    client, factory, app = notification_client
    messages = []
    class Handler(StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(3)
            self.wfile.write(b'220 local test SMTP\r\n')
            while True:
                line = self.rfile.readline()
                if not line: return
                if line.upper().startswith(b'DATA'):
                    self.wfile.write(b'354 Send message\r\n')
                    lines = []
                    while True:
                        row = self.rfile.readline()
                        if row == b'.\r\n': break
                        if not row: return
                        lines.append(row)
                    messages.append(b''.join(lines))
                elif line.upper().startswith(b'QUIT'):
                    self.wfile.write(b'221 Goodbye\r\n'); return
                self.wfile.write(b'250 OK\r\n')
    receiver = ThreadingTCPServer(('127.0.0.1', 0), Handler)
    receiver.daemon_threads = True
    thread = Thread(target=lambda: receiver.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    app.state.settings.security.smtp_allow_private_hosts = ('127.0.0.1',)
    draft = dict(EMAIL, smtp_host='127.0.0.1', smtp_port=receiver.server_address[1], smtp_security='none')
    draft.pop('smtp_password')
    try:
        result = client.post(ROOT + '/test-email', json=draft)
        assert result.status_code == 200, result.text
        assert len(messages) == 1 and b'receiver@example.com' in messages[0]
        with factory() as db: assert db.get(NotificationSetting, 1).smtp_host is None
        assert client.put(ROOT, json=dict(draft, email_verification_token=result.json()['verification_token'])).status_code == 200
        assert len(messages) == 1  # Save must never send another message.
    finally:
        receiver.shutdown(); receiver.server_close(); thread.join(2)


def test_unicode_proof_is_rejected_and_unrelated_cookies_do_not_break_session_binding(setup):
    client, _, _ = setup
    token = client.post(ROOT + '/test-email', json=EMAIL).json()['verification_token']
    assert client.put(ROOT, json=dict(EMAIL, email_verification_token='无效凭证')).status_code == 400
    client.cookies.set('display_preference', 'compact')
    assert client.put(ROOT, json=dict(EMAIL, email_verification_token=token)).status_code == 200


def test_proof_expiring_while_waiting_for_user_lock_cannot_save(setup, monkeypatch):
    client, factory, app = setup
    token = client.post(ROOT + '/test-email', json=EMAIL).json()['verification_token']
    original_lock = api.lock_user
    def expire(db, user_id):
        store = app.state.notification_verification
        entry = store._grants[(1, 'email')]
        store._grants[(1, 'email')] = (*entry[:-1], 0)
        return original_lock(db, user_id)
    monkeypatch.setattr(api, 'lock_user', expire)
    response = client.put(ROOT, json=dict(EMAIL, email_verification_token=token))
    assert response.status_code == 400 and response.json()['code'] == 'NOTIFICATION_TEST_REQUIRED'
    with factory() as db: assert db.get(NotificationSetting, 1).smtp_host is None
