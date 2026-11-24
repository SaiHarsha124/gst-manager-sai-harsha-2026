import os
import tempfile

# Use a temporary SQLite database for automated tests.
_f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_f.close()

os.environ["DATABASE_URL"] = f"sqlite:///{_f.name}"

# Test-only secret key (at least 64 characters).
# Never use this key in production.
os.environ["SECRET_KEY"] = "test-only-secret-key-" + ("x" * 64)

DB_PATH = _f.name