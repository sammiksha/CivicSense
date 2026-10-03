import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["ANTHROPIC_API_KEY"] = ""          # tests always run offline/deterministic
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
