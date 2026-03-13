import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"

if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

if "paramiko" not in sys.modules:
    class _FakeSSHException(Exception):
        pass

    class _FakeKeyLoader:
        @staticmethod
        def from_private_key_file(path):
            return path

    class _FakeSSHClient:
        def load_system_host_keys(self):
            return None

        def set_missing_host_key_policy(self, policy):
            return None

        def connect(self, *args, **kwargs):
            return None

        def close(self):
            return None

    sys.modules["paramiko"] = types.SimpleNamespace(
        SSHException=_FakeSSHException,
        Ed25519Key=_FakeKeyLoader,
        RSAKey=_FakeKeyLoader,
        SSHClient=_FakeSSHClient,
        AutoAddPolicy=lambda: object(),
    )

if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = types.SimpleNamespace(secrets={})
