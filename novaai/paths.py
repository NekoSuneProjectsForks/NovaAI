from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
AUDIO_DIR = ROOT_DIR / "audio"
STATIC_DIR = ROOT_DIR / "novaai" / "static"
AVATAR_UPLOADS_DIR = DATA_DIR / "avatars"
PROFILE_PATH = DATA_DIR / "profile.json"
PROFILES_PATH = DATA_DIR / "profiles.json"
HISTORY_PATH = DATA_DIR / "history.jsonl"
UPDATE_STATE_PATH = DATA_DIR / "update_state.json"
VERSION_PATH = ROOT_DIR / "VERSION"

XTTS_STREAM_END = object()
