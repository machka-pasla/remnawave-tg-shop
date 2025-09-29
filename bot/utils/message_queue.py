import asyncio
import logging
from typing import Dict, Any, Callable, Awaitable, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import deque
from aiogram import Bot


@dataclass
class QueuedMessage:
    """Represents a queued message with all necessary parameters"""
    chat_id: int
    method_name: str  # 'send_message', 'edit_message_text', etc.
    kwargs: Dict[str, Any]
    callback: Optional[Callable[[Any], Awaitable[None]]] = None  # Optional callback for result


class MessageQueue:
    """Message queue with rate limiting for Telegram API"""
    
    def __init__(self, messages_per_second: float, burst_size: int = 5):
        self.messages_per_second = messages_per_second
        self.burst_size = burst_size
        self.queue: deque[QueuedMessage] = deque()
        self.last_send_times: deque[datetime] = deque()
        self.is_processing = False
        self.delay_between_messages = 1.0 / messages_per_second
        
    async def add_message(self, message: QueuedMessage) -> None:
        """Add message to queue"""
        self.queue.append(message)
        if not self.is_processing:
            asyncio.create_task(self._process_queue())
    
    async def _process_queue(self) -> None:
        """Process messages from queue with rate limiting"""
        if self.is_processing:
            return
            
        self.is_processing = True
        
        try:
            while self.queue:
                # Check if we need to wait
                await self._wait_if_needed()
                
                # Get and process next message
                message = self.queue.popleft()
                try:
                    await self._send_message(message)
                    self.last_send_times.append(datetime.now())
                    
                    # Keep only recent send times (last minute)
                    cutoff_time = datetime.now() - timedelta(seconds=60)
                    while self.last_send_times and self.last_send_times[0] < cutoff_time:
                        self.last_send_times.popleft()
                        
                except Exception as e:
                    logging.error(f"Failed to send queued message to {message.chat_id}: {e}")
                    
        finally:
            self.is_processing = False
    
    async def _wait_if_needed(self) -> None:
        """Wait if we need to respect rate limits"""
        if not self.last_send_times:
            return
            
        # Calculate time since last message
        time_since_last = (datetime.now() - self.last_send_times[-1]).total_seconds()
        
        if time_since_last < self.delay_between_messages:
            wait_time = self.delay_between_messages - time_since_last
            await asyncio.sleep(wait_time)
    
    async def _send_message(self, message: QueuedMessage) -> Any:
        """Send a single message - to be implemented by subclass"""
        raise NotImplementedError("Subclass must implement _send_message")


class TelegramMessageQueue(MessageQueue):
    """Telegram-specific message queue"""
    
    def __init__(self, bot: Bot, messages_per_second: float, burst_size: int = 5):
        super().__init__(messages_per_second, burst_size)
        self.bot = bot
    
    async def _send_message(self, message: QueuedMessage) -> Any:
        """Send message using bot method"""
        method = getattr(self.bot, message.method_name)
        result = await method(chat_id=message.chat_id, **message.kwargs)
        
        # Call callback if provided
        if message.callback:
            await message.callback(result)
            
        return result


class MessageQueueManager:
    """Manager for different types of message queues"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        
        # Different queues for different types of chats
        self.group_queue = TelegramMessageQueue(
            bot=bot,
            messages_per_second=15/60,  # 15 messages per minute for groups
            burst_size=3
        )
        
        self.user_queue = TelegramMessageQueue(
            bot=bot, 
            messages_per_second=25,  # 25 messages per second for users
            burst_size=10
        )
    
    def _is_group_chat(self, chat_id: int) -> bool:
        """Check if chat_id belongs to a group or channel"""
        return str(chat_id).startswith('-100')
    
    async def send_message(self, chat_id: int, **kwargs) -> None:
        """Queue a send_message call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_message',
            kwargs=kwargs
        )
        await queue.add_message(message)
    
    async def edit_message_text(self, chat_id: int, **kwargs) -> None:
        """Queue an edit_message_text call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='edit_message_text',
            kwargs=kwargs
        )
        await queue.add_message(message)
    
    async def send_document(self, chat_id: int, **kwargs) -> None:
        """Queue a send_document call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_document',
            kwargs=kwargs
        )
        await queue.add_message(message)
    
    async def send_photo(self, chat_id: int, **kwargs) -> None:
        """Queue a send_photo call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_photo',
            kwargs=kwargs
        )
        await queue.add_message(message)

    async def send_video(self, chat_id: int, **kwargs) -> None:
        """Queue a send_video call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_video',
            kwargs=kwargs
        )
        await queue.add_message(message)

    async def send_animation(self, chat_id: int, **kwargs) -> None:
        """Queue a send_animation (GIF) call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_animation',
            kwargs=kwargs
        )
        await queue.add_message(message)

    async def send_audio(self, chat_id: int, **kwargs) -> None:
        """Queue a send_audio call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_audio',
            kwargs=kwargs
        )
        await queue.add_message(message)

    async def send_voice(self, chat_id: int, **kwargs) -> None:
        """Queue a send_voice call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_voice',
            kwargs=kwargs
        )
        await queue.add_message(message)

    async def send_sticker(self, chat_id: int, **kwargs) -> None:
        """Queue a send_sticker call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_sticker',
            kwargs=kwargs
        )
        await queue.add_message(message)

    async def send_video_note(self, chat_id: int, **kwargs) -> None:
        """Queue a send_video_note call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(
            chat_id=chat_id,
            method_name='send_video_note',
            kwargs=kwargs
        )
        await queue.add_message(message)
    
    async def answer_callback_query(self, callback_query_id: str, **kwargs) -> None:
        """Send callback query answer immediately (not rate limited)"""
        await self.bot.answer_callback_query(callback_query_id, **kwargs)
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get statistics about queues"""
        return {
            "group_queue_size": len(self.group_queue.queue),
            "user_queue_size": len(self.user_queue.queue),
            "group_queue_processing": self.group_queue.is_processing,
            "user_queue_processing": self.user_queue.is_processing,
            "group_recent_sends": len(self.group_queue.last_send_times),
            "user_recent_sends": len(self.user_queue.last_send_times)
        }


# Global queue manager instance
_queue_manager: Optional[MessageQueueManager] = None


def init_queue_manager(bot: Bot) -> MessageQueueManager:
    """Initialize global queue manager"""
    global _queue_manager
    _queue_manager = MessageQueueManager(bot)
    return _queue_manager


def get_queue_manager() -> Optional[MessageQueueManager]:
    """Get global queue manager instance"""
    return _queue_manager