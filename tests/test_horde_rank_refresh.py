"""Exercise the Me tab's asynchronous lookup without opening a window."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from lib.utilities import horde_ranks


@pytest.mark.parametrize('change', ['refresh', 'account', 'destroy'])
def test_old_rank_response_cannot_overwrite_current_dialog(monkeypatch, change):
    tree = ast.parse((Path(__file__).parents[1] / 'lib/guis/social_gui.py').read_text(encoding='utf-8'))
    method = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == 'SocialDialog'
                  for n in c.body if isinstance(n, ast.FunctionDef) and n.name == '_refresh_horde_ranks')
    workers = []; callbacks = []
    namespace = dict(logger=logging.getLogger(__name__),
        threading=SimpleNamespace(Thread=lambda target, **kw: SimpleNamespace(start=lambda: workers.append(target))),
        wx=SimpleNamespace(CallAfter=lambda fn, text: callbacks.append((fn, text))))
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<rank-refresh>', 'exec'), namespace)
    monkeypatch.setattr(horde_ranks.HordeRankAPI, 'query', lambda self: None)
    dialog = SimpleNamespace(_horde_refresh_id=0, _is_destroying=False, horde_rank_text=Mock(),
        social_manager=SimpleNamespace(auth=SimpleNamespace(is_valid=True, account_id='first')))
    namespace['_refresh_horde_ranks'](dialog)
    workers[0]()
    if change == 'refresh': dialog._horde_refresh_id += 1
    elif change == 'account': dialog.social_manager.auth.account_id = 'second'
    else: dialog._is_destroying = True
    dialog.horde_rank_text.reset_mock()
    callbacks[0][0](callbacks[0][1])
    dialog.horde_rank_text.SetValue.assert_not_called()
