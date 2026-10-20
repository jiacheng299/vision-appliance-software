from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='VISION_', extra='ignore')
    var_root: Path = ROOT / 'var'
    frontend_dist: Path = ROOT / 'frontend' / 'dist'
    ffmpeg: str = 'ffmpeg'
    ffprobe: str = 'ffprobe'
    media_timeout_seconds: int = 120
    worker_lease_seconds: int = 180
    worker_poll_seconds: float = 1.0
    max_chunk_bytes: int = 8 * 1024 * 1024
    version: str = '0.1.0'

    @property
    def database_url(self):
        return 'sqlite:///' + (self.var_root / 'vision.db').resolve().as_posix()

    def prepare(self):
        self.var_root = self.var_root.resolve()
        self.var_root.mkdir(parents=True, exist_ok=True)
        for name in ('uploads', 'media', 'secrets'):
            (self.var_root / name).mkdir(exist_ok=True)
