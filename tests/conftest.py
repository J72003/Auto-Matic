import os
import tempfile
import pytest


@pytest.fixture()
def client():
    # isolated, throwaway database per test session
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_PATH"] = path
    from app import create_app
    app = create_app()
    app.testing = True
    with app.test_client() as c:
        yield c
    os.remove(path)
