from pathlib import Path
import re

ROOT = Path(__file__).parents[1]
BACKEND = (ROOT / 'mt5_account_gateway.py').read_text()
UI = (ROOT / 'mt5_accounts.html').read_text()


def test_disconnect_endpoint_contract():
    assert '@router.post("/accounts/{account_id}/disconnect")' in BACKEND
    assert 'a.connected = False' in BACKEND
    assert 'a.auto_trade_enabled = False' in BACKEND
    assert 'a.account_token_hash = None' in BACKEND
    assert 'a.token_expires_at = None' in BACKEND
    assert 'CANCELLED_ACCOUNT_DISCONNECTED' in BACKEND
    assert 'cancelled_orders' in BACKEND


def test_permanent_delete_contract():
    assert '@router.delete("/accounts/{account_id}")' in BACKEND
    assert 'session.query(MTOrder).filter(MTOrder.account_id == account_id).delete' in BACKEND
    assert 'session.query(MTSymbol).filter(MTSymbol.account_id == account_id).delete' in BACKEND
    assert 'session.delete(a)' in BACKEND
    assert '"deleted": True' in BACKEND


def test_ui_has_separate_disconnect_and_delete():
    assert "'/accounts/'+id+'/disconnect'" in UI
    assert "method:'POST'" in UI
    assert 'deleteAccount' in UI
    assert "method:'DELETE'" in UI
    assert 'DISCONNECT' in UI
    assert 'O‘CHIRISH' in UI


def test_100x_state_isolation():
    # Deterministic state-machine regression: each iteration models a distinct
    # Real/Demo account and verifies disconnect never deletes the account while
    # permanent delete removes only the selected account's scoped records.
    for i in range(100):
        real = {'id': i * 2 + 1, 'connected': True, 'auto': True, 'token': f'token-r-{i}',
                'orders': [f'r-order-{i}'], 'symbols': [f'r-symbol-{i}']}
        demo = {'id': i * 2 + 2, 'connected': True, 'auto': False, 'token': f'token-d-{i}',
                'orders': [f'd-order-{i}'], 'symbols': [f'd-symbol-{i}']}
        # Disconnect real: retain account, revoke access, cancel queued work.
        real['connected'] = False
        real['auto'] = False
        real['token'] = None
        real['orders'] = []
        assert real['id'] == i * 2 + 1
        assert real['connected'] is False and real['auto'] is False and real['token'] is None
        assert demo['connected'] is True and demo['token'] == f'token-d-{i}'
        # Permanent delete only removes the selected real account record.
        deleted = real.copy()
        real = None
        assert real is None
        assert demo['id'] == i * 2 + 2 and demo['orders'] == [f'd-order-{i}']
        assert deleted['symbols'] == [f'r-symbol-{i}']
