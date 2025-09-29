import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Update
from sqlalchemy.orm import sessionmaker


class DBSessionMiddleware(BaseMiddleware):

    def __init__(self, async_session_factory: sessionmaker):
        super().__init__()
        self.async_session_factory = async_session_factory

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        if self.async_session_factory is None:
            logging.critical("DBSessionMiddleware: async_session_factory is None!")
            raise RuntimeError(
                "async_session_factory not provided to DBSessionMiddleware"
            )

        async with self.async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)

                await session.commit()
                return result
            except Exception:
                await session.rollback()
                logging.error(
                    "DBSessionMiddleware: Exception caused rollback.", exc_info=True
                )
                raise

