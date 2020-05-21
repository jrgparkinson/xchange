from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    path('', views.index, name='index'),

    path('register/', views.register),
    # path('login/', auth_views.login, {'template_name': 'login.html'}, name='login'),
    path('login/', auth_views.LoginView.as_view(redirect_authenticated_user=True)),
    path('logout/', views.logout_view),
    path('profile/', views.profile),
    path('dashboard/', views.dashboard),
    path('trades/', views.trades),
    path('marketplace/', views.marketplace),


    path("respond_to_open_trade", views.temp, name="respond_to_open_trade")
]