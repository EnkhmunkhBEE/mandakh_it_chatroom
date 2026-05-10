from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.utils.text import slugify
from .models import Room, Message, Profile
import json
import os


def _avatar_url(user):
    try:
        p = user.profile
        if p.avatar:
            return p.avatar.url
    except Exception:
        pass
    return None


class LoginView(View):
    template_name = 'chat/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('room_list')
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get('next', 'room_list'))
        messages.error(request, 'Invalid username or password.')
        return render(request, self.template_name, {'username': username})


class RegisterView(View):
    template_name = 'chat/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('room_list')
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        errors = []
        if not username:
            errors.append('Username is required.')
        elif User.objects.filter(username=username).exists():
            errors.append('Username already taken.')
        if len(password1) < 4:
            errors.append('Password must be at least 4 characters.')
        if password1 != password2:
            errors.append('Passwords do not match.')
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, self.template_name, {'username': username})
        user = User.objects.create_user(username=username, password=password1)
        login(request, user)
        messages.success(request, f'Welcome, {username}!')
        return redirect('room_list')


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect('login')


class ProfileView(LoginRequiredMixin, View):
    login_url = '/login/'
    template_name = 'chat/profile.html'

    def get(self, request, username=None):
        if username:
            target = get_object_or_404(User, username=username)
        else:
            target = request.user
        profile, _ = Profile.objects.get_or_create(user=target)
        is_own = target == request.user
        return render(request, self.template_name, {
            'target': target,
            'profile': profile,
            'is_own': is_own,
        })

    def post(self, request, username=None):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        display_name = request.POST.get('display_name', '').strip()
        bio = request.POST.get('bio', '').strip()
        clear_avatar = request.POST.get('clear_avatar') == '1'
        profile.display_name = display_name[:50]
        profile.bio = bio[:160]
        if clear_avatar and profile.avatar:
            try:
                if os.path.isfile(profile.avatar.path):
                    os.remove(profile.avatar.path)
            except Exception:
                pass
            profile.avatar = None
        if 'avatar' in request.FILES:
            f = request.FILES['avatar']
            allowed = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
            if f.content_type in allowed:
                try:
                    if profile.avatar and os.path.isfile(profile.avatar.path):
                        os.remove(profile.avatar.path)
                except Exception:
                    pass
                profile.avatar = f
            else:
                messages.error(request, 'Please upload a JPEG, PNG, GIF or WebP image.')
                return redirect('profile_own')
        profile.save()
        messages.success(request, 'Profile updated!')
        return redirect('profile_own')


class RoomListView(LoginRequiredMixin, View):
    login_url = '/login/'
    template_name = 'chat/room_list.html'

    def get(self, request):
        rooms = Room.objects.all().prefetch_related('members')
        my_rooms = rooms.filter(members=request.user)
        other_rooms = rooms.exclude(members=request.user)
        return render(request, self.template_name, {
            'my_rooms': my_rooms,
            'other_rooms': other_rooms,
        })

    def post(self, request):
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Room name is required.')
            return redirect('room_list')
        slug = slugify(name)
        if Room.objects.filter(slug=slug).exists():
            messages.error(request, 'A room with that name already exists.')
            return redirect('room_list')
        room = Room.objects.create(
            name=name, slug=slug, description=description, created_by=request.user
        )
        room.members.add(request.user)
        messages.success(request, f'Room "{name}" created!')
        return redirect('room_detail', slug=room.slug)


class RoomDetailView(LoginRequiredMixin, View):
    login_url = '/login/'
    template_name = 'chat/room_detail.html'

    def get(self, request, slug):
        room = get_object_or_404(Room, slug=slug)
        if request.user not in room.members.all():
            room.members.add(request.user)
        msgs = room.messages.select_related('author', 'author__profile').order_by('timestamp')
        return render(request, self.template_name, {
            'room': room,
            'messages': msgs,
        })

    def post(self, request, slug):
        room = get_object_or_404(Room, slug=slug)
        content = request.POST.get('content', '').strip()
        if content:
            Message.objects.create(room=room, author=request.user, content=content)
        return redirect('room_detail', slug=slug)


class MessageSendView(LoginRequiredMixin, View):
    login_url = '/login/'

    def post(self, request, slug):
        room = get_object_or_404(Room, slug=slug)
        try:
            data = json.loads(request.body)
            content = data.get('content', '').strip()
        except (json.JSONDecodeError, AttributeError):
            content = request.POST.get('content', '').strip()
        if not content:
            return JsonResponse({'error': 'Empty message'}, status=400)
        msg = Message.objects.create(room=room, author=request.user, content=content)
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return JsonResponse({
            'id': msg.id,
            'author': msg.author.username,
            'display_name': profile.get_display_name(),
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%H:%M'),
            'is_own': True,
            'avatar_url': _avatar_url(msg.author),
        })


class MessagePollView(LoginRequiredMixin, View):
    login_url = '/login/'

    def get(self, request, slug):
        room = get_object_or_404(Room, slug=slug)
        after_id = int(request.GET.get('after', 0))
        msgs = room.messages.filter(id__gt=after_id).select_related('author', 'author__profile')
        data = [{
            'id': m.id,
            'author': m.author.username,
            'display_name': m.author.profile.get_display_name() if hasattr(m.author, 'profile') else m.author.username,
            'content': m.content,
            'timestamp': m.timestamp.strftime('%H:%M'),
            'is_own': m.author == request.user,
            'avatar_url': _avatar_url(m.author),
        } for m in msgs]
        return JsonResponse({'messages': data})


class MessageDeleteView(LoginRequiredMixin, View):
    login_url = '/login/'

    def post(self, request, pk):
        msg = get_object_or_404(Message, pk=pk)
        if msg.author != request.user:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        msg.delete()
        return JsonResponse({'deleted': pk})


class RoomLeaveView(LoginRequiredMixin, View):
    login_url = '/login/'

    def post(self, request, slug):
        room = get_object_or_404(Room, slug=slug)
        room.members.remove(request.user)
        messages.info(request, f'You left "{room.name}".')
        return redirect('room_list')
