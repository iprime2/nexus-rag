"""Redis client factory (redis-py, asyncio API).

One client per process. It holds a connection pool internally, so it is
created at startup and closed at shutdown, like the database engine.
"""

from redis.asyncio import Redis

from app.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password.get_secret_value() if settings.redis_password else None,
        # Without timeouts, a network partition can hang a request forever.
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=5,
    )
