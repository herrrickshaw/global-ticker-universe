import os
import sys

# make the repo root importable so `import global_tickers` / `import universe_builder` work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
