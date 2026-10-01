import pytest
from pydantic import ValidationError
from app.config import ConfigError
from app.errors import AppError
import json
import tempfile
from datetime import datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import Integer, create_engine, update
from sqlalchemy.orm import sessionmaker

from app.config import load_settings
from app.models import Base, User, BillPlan, NotificationSetting, NotificationRecord
from app.schemas import NotificationSettingsPatch
from app.services import notifications, logging


def test_quoted_false_is_rejected(tmp_path):
    source=(Path(__file__).resolve().parents[2] / 'config/config.example.toml').read_text()
    path=tmp_path/'config.toml'
    path.write_text(source.replace('enabled = true', 'enabled = "false"'))
    with pytest.raises(ConfigError):
        load_settings(path)


def test_login_failure_has_explicit_result(tmp_path):
    settings=SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path)))
    logging.write_user_log(settings,user_id=1,level='WARNING',module='auth',event='login_failed',
                           request_id='test',message='登录失败',data={'reason':'AUTH_INVALID_CREDENTIALS'},result='failure')
    record=json.loads(next((tmp_path/'users/1').glob('*.log')).read_text())
    assert record['result']=='failure'


def test_archive_failure_cleans_temporary_file(tmp_path):
    settings=SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path/'logs')))
    directory=tmp_path/'logs/system'
    directory.mkdir(parents=True)
    (directory/'2026-10-01.log').write_text('{}')
    with patch.object(tempfile,'tempdir',str(tmp_path)), patch.object(logging.ZipFile,'write',side_effect=OSError('disk full')):
        try:
            logging.create_log_archive(settings,'system')
        except OSError:
            pass
    assert len(list(tmp_path.glob('subledger-logs-*.zip')))==0


def test_notification_schema_rejects_overlong_database_fields():
    with pytest.raises(ValidationError):
        NotificationSettingsPatch(sender_name='x'*129, smtp_username='x'*256)


@pytest.mark.parametrize('changed_field', ['user', 'channel', 'reminder', 'time'])
def test_disabled_user_and_channel_stop_remaining_notifications(tmp_path, changed_field):
    engine=create_engine('sqlite://')
    with patch.object(NotificationRecord.__table__.c.id,'type',Integer()):
        Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    now=datetime.now(timezone.utc).replace(tzinfo=None)
    with factory() as db:
        db.add(User(id=1,username='user',password_hash='hash',role='user',is_active=True,
                    timezone='UTC',currency_code='CNY',created_at=now,updated_at=now))
        db.add(NotificationSetting(user_id=1,email_enabled=True,same_day_enabled=True,
                     advance_enabled=False,advance_time=time(0),same_day_time=time(0),updated_at=now))
        db.flush()
        for i in (1,2):
            db.add(BillPlan(id=i,user_id=1,name=f'plan-{i}',amount=1,first_due_date=now.date(),
                           cycle_type='once',is_enabled=True,created_at=now,updated_at=now))
        db.commit()
    sent=[]
    from sqlalchemy import event
    changed = False
    @event.listens_for(factory, 'after_commit')
    def controlled(db):
        nonlocal changed
        if len(sent)==1 and not changed:
            changed = True
            with factory() as other:
                if changed_field == 'user':
                    other.execute(update(User).where(User.id==1).values(is_active=False))
                else:
                    values = {'channel': {'email_enabled': False}, 'reminder': {'same_day_enabled': False}, 'time': {'same_day_time': time(23,59)}}[changed_field]
                    other.execute(update(NotificationSetting).where(NotificationSetting.user_id==1).values(**values))
                other.commit()
    settings=SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path/'logs')))
    with patch.object(notifications, '_prepare_delivery', return_value=('smtp.example.com', [])), patch.object(notifications,'_send_email',side_effect=lambda *args:sent.append(args[3])):
        notifications.check_notifications(SimpleNamespace(session=factory),settings,None)
    assert len(sent)==1
    engine.dispose()


def test_inflight_login_cannot_create_session_after_admin_password_reset(tmp_path):
    from app.api import users as users_api
    from app.api.dependencies import get_current_user
    from app.schemas import AdminPasswordReset
    from app.security import LoginFailureLimiter
    from app.services.auth import authenticate_user, create_session
    from app.models import SessionRecord
    engine=create_engine('sqlite://')
    with patch.object(SessionRecord.__table__.c.id,'type',Integer()):
        Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    now=datetime.now(timezone.utc).replace(tzinfo=None)
    with factory() as db:
        db.add(User(id=1,username='user',password_hash='old-password',role='user',is_active=True,
                    timezone='UTC',currency_code='CNY',created_at=now,updated_at=now))
        db.commit()
    settings=SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path/'logs')),security=SimpleNamespace(cookie_name='session'))
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)),state=SimpleNamespace(request_id='audit'))
    with factory() as login_db, patch('app.services.auth.verify_password',side_effect=lambda hashed,plain:hashed==plain), patch.object(users_api,'hash_password',side_effect=lambda plain:plain):
        user=authenticate_user(login_db,'user','old-password',LoginFailureLimiter())
        with factory() as reset_db:
            users_api.reset_password(1,AdminPasswordReset(password='new-password'),request,SimpleNamespace(id=0),reset_db)
        # The already-authenticated request resumes after reset completed.
        with pytest.raises(AppError) as caught:
            create_session(login_db,user,7)
        assert caught.value.code == 'AUTH_INVALID_CREDENTIALS'
        login_db.rollback()
    with factory() as db:
        assert db.get(User,1).password_hash=='new-password'
        assert db.query(SessionRecord).count() == 0
    engine.dispose()

@pytest.mark.parametrize('source,replacement', [
    ('enabled = true', 'enabled = "false"'),
    ('[app]', 'app = false\n[unused_app]'),
    ('port = 3306', 'port = true'),
    ('pool_size = 5', 'pool_size = "5"'),
        ('level = "INFO"', 'level = "INVALID"'),
])
def test_config_rejects_invalid_types_and_levels(tmp_path, source, replacement):
    config = (Path(__file__).resolve().parents[2] / 'config/config.example.toml').read_text()
    assert source in config
    path = tmp_path / 'config.toml'
    path.write_text(config.replace(source, replacement))
    with pytest.raises(ConfigError):
        load_settings(path)


def test_log_level_filters_and_archive_tolerates_rotation(tmp_path, monkeypatch):
    settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path), level='ERROR'))
    logging.write_system_log(settings, level='INFO', module='test', event='ignored', request_id=None, message='hidden')
    assert not (tmp_path / 'system').exists()
    logging.write_system_log(settings, level='ERROR', module='test', event='error', request_id=None, message='visible')
    assert (tmp_path / 'system').exists()
    monkeypatch.setattr(logging.ZipFile, 'write', lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    archive = logging.create_log_archive(settings, 'system')
    try:
        with logging.ZipFile(archive) as zipped:
            assert zipped.namelist() == []
    finally:
        archive.unlink()
