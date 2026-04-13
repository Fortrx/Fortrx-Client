"""
E2E test configuration and fixtures for Fortress messenger.
"""

import pytest
import asyncio
import httpx
import os
import time


SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def test_suffix():
    """Generate unique suffix for test users to avoid conflicts."""
    return str(int(time.time() * 1000) % 1000000)


@pytest.fixture(scope="session")
def server_url():
    """Return the base URL to the Fortress server."""
    return SERVER_URL


@pytest.fixture(scope="session")
def alice_storage(tmp_path_factory):
    """Create temporary storage directory for Alice."""
    path = tmp_path_factory.mktemp("alice")
    return path


@pytest.fixture(scope="session")
def bob_storage(tmp_path_factory):
    """Create temporary storage directory for Bob."""
    path = tmp_path_factory.mktemp("bob")
    return path


@pytest.fixture(scope="session")
def storage_password():
    """Shared storage password for encryption."""
    return "test-storage-password-e2e"


@pytest.fixture(scope="session")
def alice_client(server_url):
    """HTTP client for Alice with server base URL."""
    client = httpx.Client(base_url=server_url, timeout=30)
    yield client
    client.close()


@pytest.fixture(scope="session")
def bob_client(server_url):
    """HTTP client for Bob with server base URL."""
    client = httpx.Client(base_url=server_url, timeout=30)
    yield client
    client.close()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
