import asyncio
from functools import wraps
from typing import TypeVar, Callable, Any

from utils.customprint import CustomPrint
from data import config

T = TypeVar("T")

def retry_async(
    attempts: int = None,  
    delay: float = 1.0,
    backoff: float = 2.0,
    default_value: Any = None,
):
    """
    Async retry decorator with exponential backoff.
    If attempts is not provided, uses SETTINGS.ATTEMPTS from config.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retry_attempts = attempts if attempts is not None else config.ATTEMPTS
            current_delay = delay

            for attempt in range(retry_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt < retry_attempts - 1:  # Don't sleep on the last attempt
                        CustomPrint().warning(
                            f"Attempt {attempt + 1}/{retry_attempts} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {current_delay:.1f} seconds..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        CustomPrint().warning(
                            f"All {retry_attempts} attempts failed for {func.__name__}: {str(e)}"
                        )
                        raise e

            return default_value

        return wrapper

    return decorator