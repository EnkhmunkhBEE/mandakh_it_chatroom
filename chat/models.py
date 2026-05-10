from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import os


def avatar_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'avatars/{instance.user.id}.{ext}'


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to=avatar_upload_path, null=True, blank=True)
    bio = models.CharField(max_length=160, blank=True)
    display_name = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f'{self.user.username} profile'

    def get_display_name(self):
        return self.display_name or self.user.username

    def get_avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return None


@receiver(post_save, sender=User)
def create_or_save_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        Profile.objects.get_or_create(user=instance)


class Room(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='rooms_created')
    members = models.ManyToManyField(User, related_name='rooms', blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_last_message(self):
        return self.messages.order_by('-timestamp').first()


class Message(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f'{self.author.username}: {self.content[:50]}'
