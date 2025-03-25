import fnmatch
import logging
import os

from redis.asyncio import Redis

# See https://stackoverflow.com/a/77007723/15965186
logger = logging.getLogger("uvicorn.error")


def matches_pattern(path: str, pattern: str) -> bool:
    """
    Checks if the given path matches the provided wildcard pattern.

    This function uses Unix shell-style matching with fnmatch, but also treats
    a pattern ending in "/*" as matching the exact prefix as well as any subpath.
    For example:
        - Pattern "items/*" will match both "items" and "items/MLA123".

    Args:
        path (str): The path string to test.
        pattern (str): The wildcard pattern to match against.

    Returns:
        bool: True if the path matches the pattern, False otherwise.
    """
    # Remove a leading slash for consistency, if present.
    if path.startswith("/"):
        path = path[1:]

    # If the pattern ends with "/*", check if the path matches the prefix.
    if pattern.endswith("/*"):
        prefix = pattern[:-2]  # Remove "/*" from the end
        if path == prefix:
            return True

    return fnmatch.fnmatch(path, pattern)


async def setup_redis_client():
    """
    Based on https://www.reddit.com/r/FastAPI/comments/1e67aug/how_to_use_redis/
    """
    redis_client = Redis(
        host=os.environ["REDIS_HOST"],
        port=os.environ["REDIS_PORT"],
        password=os.environ["REDIS_PASSWORD"],
        # decode_responses=True ensures strings are returned as Python str
        decode_responses=True,
    )
    try:
        await redis_client.ping()
        logger.info("Redis is connected")
    except Exception as e:
        logger.error("Redis is not connected: %s", e)
        raise Exception(f"Redis is not connected: {e}")
    return redis_client
