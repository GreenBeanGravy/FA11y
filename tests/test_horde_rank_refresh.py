"""The Social page's Horde rank request returns text for every auth state."""
from types import SimpleNamespace
import pytest
from lib.shell.handlers import social
from lib.utilities import horde_ranks
from lib.utilities.epic_quests import QuestQueryError


def _manager(monkeypatch, auth):
    monkeypatch.setattr(social, '_require', lambda: SimpleNamespace(auth=auth))


def test_signed_out_says_to_sign_in(monkeypatch):
    _manager(monkeypatch, None)
    assert social.social_horde_rank({})['text'].startswith('Sign in through FA11y')


@pytest.mark.parametrize('error,start', [
    (QuestQueryError('Try later.'), 'Horde rank unavailable. Try later.'),
    (RuntimeError('boom'), 'Could not load your Horde rank. Refresh to retry.'),
])
def test_errors_become_text(monkeypatch, error, start):
    _manager(monkeypatch, SimpleNamespace(is_valid=True, account_id='a'))
    def fail(self):
        raise error
    monkeypatch.setattr(horde_ranks.HordeRankAPI, 'query', fail)
    assert social.social_horde_rank({})['text'].startswith(start)


def test_snapshot_text(monkeypatch):
    _manager(monkeypatch, SimpleNamespace(is_valid=True, account_id='a'))
    monkeypatch.setattr(horde_ranks.HordeRankAPI, '__init__', lambda self, auth: None)
    monkeypatch.setattr(horde_ranks.HordeRankAPI, 'query', lambda self: None)
    monkeypatch.setattr(horde_ranks, 'rank_text', lambda snap=None, error=None: f'ok {snap}')
    assert social.social_horde_rank({})['text'] == 'ok None'
