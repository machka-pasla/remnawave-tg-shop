from typing import List, Union, Optional
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, User

from bot.utils.id_bridge import IdBridge


class AdminFilter(Filter):

    def __init__(self, admin_ids: List[Union[int, str]], id_bridge: Optional[IdBridge] = None):
        self.admin_ids = admin_ids
        self.id_bridge = id_bridge

    async def __call__(self, event: Union[Message, CallbackQuery],
                       event_from_user: User) -> bool:
        if not event_from_user:
            return False
        if not self.admin_ids:
            return False
        bridge = self.id_bridge
        if bridge:
            return bridge.is_admin(event_from_user.id, self.admin_ids)
        return event_from_user.id in self.admin_ids
