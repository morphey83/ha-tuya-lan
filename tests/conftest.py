import sys
from pathlib import Path

_CC = Path(__file__).resolve().parent.parent / "custom_components" / "tuya_lan"
sys.path.insert(0, str(_CC))
