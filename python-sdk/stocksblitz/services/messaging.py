"""
Messaging Service - Send and receive messages.

Provides functionality for inter-strategy communication, notifications,
and message queuing.
"""

import uuid
import threading
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime
from collections import defaultdict

from ..enums import MessageType
from ..types import Message, MessageCallback
from ..exceptions import APIError


class MessagingService:
    """
    Messaging service for communication.

    Features:
    - Send/receive messages
    - Topic-based pub/sub
    - Message queues
    - Callbacks for incoming messages

    Examples:
        # Get messaging service
        messaging = client.messaging

        # Subscribe to topic
        def on_message(msg: Message):
            print(f"Received: {msg.content}")

        messaging.subscribe("trade-signals", on_message)

        # Publish message
        messaging.publish(
            topic="trade-signals",
            content={"symbol": "NIFTY50", "signal": "BUY"}
        )

        # Send direct message
        messaging.send(
            recipient="strategy-2",
            content="Order executed"
        )
    """

    def __init__(self, api_client: 'APIClient'):
        """Initialize messaging service."""
        self._api = api_client
        self._messages: Dict[str, Message] = {}
        self._queues: Dict[str, List[Message]] = defaultdict(list)
        self._subscribers: Dict[str, List[MessageCallback]] = defaultdict(list)
        self._lock = threading.Lock()

    def send(
        self,
        content: Union[str, bytes, Dict[str, Any]],
        recipient: Optional[str] = None,
        message_type: MessageType = MessageType.TEXT,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Send a direct message.

        Args:
            content: Message content
            recipient: Recipient identifier
            message_type: Type of message
            metadata: Additional metadata

        Returns:
            Message object

        Example:
            msg = messaging.send(
                content="Trade executed",
                recipient="strategy-2",
                metadata={"order_id": "12345"}
            )
        """
        message_id = str(uuid.uuid4())
        msg = Message(
            message_id=message_id,
            message_type=message_type,
            content=content,
            recipient=recipient,
            metadata=metadata or {}
        )

        with self._lock:
            self._messages[message_id] = msg
            if recipient:
                self._queues[recipient].append(msg)

        # TODO: Send via API
        # self._api.post("/messaging/send", json=msg.to_dict())

        return msg

    def receive(
        self,
        recipient: str,
        mark_read: bool = True
    ) -> List[Message]:
        """
        Receive messages for recipient.

        Args:
            recipient: Recipient identifier
            mark_read: Mark messages as read

        Returns:
            List of messages

        Example:
            messages = messaging.receive("my-strategy")
            for msg in messages:
                print(msg.content)
        """
        with self._lock:
            messages = self._queues.get(recipient, []).copy()
            if mark_read:
                for msg in messages:
                    msg.mark_as_read()

        # TODO: Fetch from API
        # response = self._api.get(f"/messaging/receive?recipient={recipient}")

        return messages

    def publish(
        self,
        topic: str,
        content: Union[str, bytes, Dict[str, Any]],
        message_type: MessageType = MessageType.JSON,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Publish message to topic (pub/sub).

        Args:
            topic: Topic name
            content: Message content
            message_type: Type of message
            metadata: Additional metadata

        Returns:
            Message object

        Example:
            messaging.publish(
                topic="trade-signals",
                content={
                    "symbol": "NIFTY50",
                    "signal": "BUY",
                    "price": 24000
                }
            )
        """
        message_id = str(uuid.uuid4())
        msg = Message(
            message_id=message_id,
            message_type=message_type,
            content=content,
            metadata=metadata or {}
        )

        with self._lock:
            self._messages[message_id] = msg

        # Trigger subscribers
        self._notify_subscribers(topic, msg)

        # TODO: Publish via API
        # self._api.post(f"/messaging/publish/{topic}", json=msg.to_dict())

        return msg

    def subscribe(
        self,
        topic: str,
        callback: MessageCallback
    ) -> None:
        """
        Subscribe to topic.

        Args:
            topic: Topic name
            callback: Callback function (receives Message)

        Example:
            def handle_signals(msg: Message):
                data = msg.content
                if data.get("signal") == "BUY":
                    print(f"Buy signal for {data['symbol']}")

            messaging.subscribe("trade-signals", handle_signals)
        """
        with self._lock:
            self._subscribers[topic].append(callback)

        # TODO: Subscribe via API
        # self._api.post(f"/messaging/subscribe/{topic}")

    def unsubscribe(
        self,
        topic: str,
        callback: Optional[MessageCallback] = None
    ) -> None:
        """
        Unsubscribe from topic.

        Args:
            topic: Topic name
            callback: Specific callback (or None to unsubscribe all)

        Example:
            messaging.unsubscribe("trade-signals")
            messaging.unsubscribe("trade-signals", handle_signals)
        """
        with self._lock:
            if callback is None:
                self._subscribers[topic].clear()
            else:
                self._subscribers[topic].remove(callback)

        # TODO: Unsubscribe via API
        # self._api.post(f"/messaging/unsubscribe/{topic}")

    def _notify_subscribers(self, topic: str, msg: Message) -> None:
        """Notify all subscribers for topic."""
        callbacks = self._subscribers.get(topic, [])
        for callback in callbacks:
            try:
                callback(msg)
            except Exception as e:
                print(f"Error in message callback: {e}")

    def get_message(self, message_id: str) -> Optional[Message]:
        """Get message by ID."""
        return self._messages.get(message_id)

    def get_messages(
        self,
        recipient: Optional[str] = None,
        unread_only: bool = False
    ) -> List[Message]:
        """
        Get messages with filters.

        Args:
            recipient: Filter by recipient
            unread_only: Only unread messages

        Returns:
            List of messages

        Example:
            # Get unread messages
            unread = messaging.get_messages(
                recipient="my-strategy",
                unread_only=True
            )
        """
        with self._lock:
            results = list(self._messages.values())

        if recipient:
            results = [m for m in results if m.recipient == recipient]
        if unread_only:
            results = [m for m in results if m.read_at is None]

        return results

    def clear_messages(
        self,
        recipient: Optional[str] = None,
        read_only: bool = True
    ) -> int:
        """
        Clear messages from history.

        Args:
            recipient: Filter by recipient
            read_only: Only clear read messages

        Returns:
            Number of messages cleared

        Example:
            count = messaging.clear_messages(read_only=True)
        """
        to_remove = self.get_messages(recipient=recipient)
        if read_only:
            to_remove = [m for m in to_remove if m.read_at is not None]

        count = 0
        with self._lock:
            for msg in to_remove:
                if msg.message_id in self._messages:
                    del self._messages[msg.message_id]
                    count += 1

        return count

    def broadcast(
        self,
        content: Union[str, Dict[str, Any]],
        message_type: MessageType = MessageType.JSON,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Broadcast message to all subscribers.

        Args:
            content: Message content
            message_type: Type of message
            metadata: Additional metadata

        Returns:
            Message object

        Example:
            messaging.broadcast({
                "type": "market-alert",
                "message": "Market closed"
            })
        """
        return self.publish(
            topic="broadcast",
            content=content,
            message_type=message_type,
            metadata=metadata
        )
