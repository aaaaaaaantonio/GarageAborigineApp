import uuid

TEST_SERVICE_KEY = "test-service-key"


def staff_headers(user_id: uuid.UUID) -> dict[str, str]:
    """Headers the bot sends to act as a staff member: X-User-Id plus the service key."""
    return {"X-User-Id": str(user_id), "X-Service-Key": TEST_SERVICE_KEY}
