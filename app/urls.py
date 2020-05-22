from django.urls import path
from django.contrib.auth import views as auth_views

from . import views, requests

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

    # JQuery
    path('retrieve_trades/', views.retrieve_trades, name="retrieve_trades"), # need name for JS lookup url
    path('create_trade/', views.create_trade, name="create_trade"),
    path("respond_to_open_trade/", views.temp, name="respond_to_open_trade"),
    path("respond_to_trade/", views.temp, name="respond_to_trade"),
    path("action_trade/", views.action_trade, name="action_trade"),
    path("get_investors/", views.get_investors, name="get_investors"),
    path("get_athletes/", views.get_athletes, name="get_athletes"),
]