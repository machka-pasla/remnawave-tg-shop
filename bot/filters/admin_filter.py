from typing import List, Union
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, User


class AdminFilter(Filter):

    def __init__(self, admin_ids: List[int]):
        self.admin_ids = admin_ids

    async def __call__(self, event: Union[Message, CallbackQuery],
                       event_from_user: User) -> bool:
        if not event_from_user:
            return False
        if not self.admin_ids:
            return False
        return event_from_user.id in self.admin_ids
