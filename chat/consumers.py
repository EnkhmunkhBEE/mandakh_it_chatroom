import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Room, Message, Profile


def _avatar_url(user):
    try:
        if user.profile.avatar:
            return user.profile.avatar.url
    except Exception:
        pass
    return None


def _display_name(user):
    try:
        return user.profile.get_display_name()
    except Exception:
        return user.username


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope['user']
        self.slug = self.scope['url_route']['kwargs']['slug']
        self.group_name = f'chat_{self.slug}'

        if not self.user.is_authenticated:
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Add user to room members
        await self.add_member()

        # Broadcast presence
        await self.channel_layer.group_send(self.group_name, {
            'type': 'presence',
            'action': 'join',
            'username': self.user.username,
            'display_name': _display_name(self.user),
            'is_admin': bool(self.user.is_staff),
        })

    async def disconnect(self, close_code):
        if not self.user.is_authenticated:
            return

        await self.channel_layer.group_send(self.group_name, {
            'type': 'presence',
            'action': 'leave',
            'username': self.user.username,
            'display_name': _display_name(self.user),
            'is_admin': bool(self.user.is_staff),
        })

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        kind = data.get('type')

        if kind == 'message':
            content = data.get('content', '').strip()
            if not content:
                return

            msg = await self.save_message(content)

            await self.channel_layer.group_send(self.group_name, {
                'type': 'chat_message',
                'id': msg['id'],
                'author': msg['author'],
                'display_name': msg['display_name'],
                'content': msg['content'],
                'timestamp': msg['timestamp'],
                'avatar_url': msg['avatar_url'],
                'is_admin': msg['is_admin'],
            })

        elif kind == 'typing':
            # broadcast typing indicator to others only
            await self.channel_layer.group_send(self.group_name, {
                'type': 'typing_indicator',
                'username': self.user.username,
                'display_name': _display_name(self.user),
                'is_typing': data.get('is_typing', False),
                'is_admin': bool(self.user.is_staff),
                'sender_channel': self.channel_name,
            })

        elif kind == 'delete':
            msg_id = data.get('id')
            if msg_id:
                deleted = await self.delete_message(msg_id)
                if deleted:
                    await self.channel_layer.group_send(self.group_name, {
                        'type': 'message_deleted',
                        'id': msg_id,
                    })

    # ── group event handlers ──────────────────────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'id': event['id'],
            'author': event['author'],
            'display_name': event['display_name'],
            'content': event['content'],
            'timestamp': event['timestamp'],
            'avatar_url': event['avatar_url'],
            'is_admin': event.get('is_admin', False),
            'is_own': event['author'] == self.user.username,
        }))

    async def typing_indicator(self, event):
        # Don't send typing back to the sender
        if event.get('sender_channel') == self.channel_name:
            return
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'username': event['username'],
            'display_name': event['display_name'],
            'is_typing': event['is_typing'],
            'is_admin': event.get('is_admin', False),
        }))

    async def presence(self, event):
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'action': event['action'],
            'username': event['username'],
            'display_name': event['display_name'],
            'is_admin': event.get('is_admin', False),
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'deleted',
            'id': event['id'],
        }))

    # ── database helpers ──────────────────────────────────────────

    @database_sync_to_async
    def save_message(self, content):
        room = Room.objects.get(slug=self.slug)
        msg = Message.objects.create(room=room, author=self.user, content=content)
        return {
            'id': msg.id,
            'author': self.user.username,
            'display_name': _display_name(self.user),
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%H:%M'),
            'avatar_url': _avatar_url(self.user),
            'is_admin': bool(self.user.is_staff),
        }

    @database_sync_to_async
    def delete_message(self, msg_id):
        try:
            msg = Message.objects.get(id=msg_id, author=self.user)
            msg.delete()
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def add_member(self):
        try:
            room = Room.objects.get(slug=self.slug)
            room.members.add(self.user)
        except Room.DoesNotExist:
            pass
