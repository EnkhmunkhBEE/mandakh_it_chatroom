from django.urls import path
from . import views

urlpatterns = [
    path('', views.RoomListView.as_view(), name='room_list'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile_own'),
    path('profile/<str:username>/', views.ProfileView.as_view(), name='profile'),
    path('room/<slug:slug>/', views.RoomDetailView.as_view(), name='room_detail'),
    path('room/<slug:slug>/leave/', views.RoomLeaveView.as_view(), name='room_leave'),
    path('message/<int:pk>/delete/', views.MessageDeleteView.as_view(), name='message_delete'),
]
