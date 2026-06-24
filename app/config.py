from pathlib import Path


APP_NAME = "AguacatIA"
APP_VERSION = "0.3.2"
APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "aguacatia.sqlite"
