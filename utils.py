import pickle
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"


def load_pickle(filename):
    path = MODEL_DIR / filename

    with open(path, "rb") as f:
        return pickle.load(f)