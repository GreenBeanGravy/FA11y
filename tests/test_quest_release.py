"""Check the public release wires the account features without decoder imports."""
import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def test_account_dialogs_import_without_decoder():
    result = subprocess.run([sys.executable, '-c', "import sys; import lib.guis.passes_gui; import lib.guis.quest_gui; import lib.monitors.quest_account_monitor; assert not any(n == 'lib.packet' or n.startswith('lib.packet.') for n in sys.modules)"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (ROOT / 'lib/packet').exists()

def test_main_wires_account_monitor_and_quest_hotkey():
    source = (ROOT / 'FA11y.py').read_text(encoding='utf-8')
    ast.parse(source)
    assert "'open quest browser': open_quest_browser" in source
    assert 'quest_account_monitor.start_monitoring()' in source
    assert source.count('quest_account_monitor.stop_monitoring()') == 2
    assert '"Fortnite Quests"' in source
    config = (ROOT / 'lib/utilities/utilities.py').read_text(encoding='utf-8')
    assert 'Open Quest Browser = lalt+q' in config
    assert 'QuestAnnouncements = true' in config
