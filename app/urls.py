from django.urls import path
from django.contrib.auth import views as auth_views
from django.contrib import admin

from . import views, requests
from app.forms import UserLoginForm

handler404 = views.handler404
handler500 = views.handler500
handler403 = views.handler403

urlpatterns = [
    path('admin', admin.site.urls, name='admin'),
    path("", views.index, name="index"),
    path("register/", views.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            authentication_form=UserLoginForm, redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("logout/", views.logout_view, name="logout"),
    path(
        "password_reset/", auth_views.PasswordResetView.as_view(), name="password_reset"
    ),
    path(
        "password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("profile/", views.profile, name="profile"),
    path("portfolio/", views.portfolio, name="portfolio"),
    path("trades/", views.trades, name="trades"),
    path("about/", views.about, name="about"),
    path("races/<int:race_id>", views.races, name="races_id"),
    path("races/", views.races, name="races"),
    path("bank/", views.bank, name="bank"),
    path("auction/", views.auction, name="auction"),
    path("marketplace/", views.marketplace, name="marketplace"),
    path("athlete/<int:athlete_id>/", views.view_athlete, name="athlete"),
    path("investor/<int:investor_id>/", views.view_investor, name="investor"),
    # JQuery
    path(
        "retrieve_trades/", views.retrieve_trades, name="retrieve_trades"
    ),  # need name for JS lookup url
    path("create_trade/", views.create_trade, name="create_trade"),
    path("respond_to_open_trade/", views.temp, name="respond_to_open_trade"),
    path("respond_to_trade/", views.temp, name="respond_to_trade"),
    path("action_trade/", views.action_trade, name="action_trade"),
    path("get_investors/", views.get_investors, name="get_investors"),
    path("get_athletes/", views.get_athletes, name="get_athletes"),
    path(
        "retrieve_athlete_value/",
        views.retrieve_athlete_value,
        name="retrieve_athlete_value",
    ),
    path(
        "retrieve_investor_portfolio/",
        views.retrieve_investor_portfolio,
        name="retrieve_investor_portfolio",
    ),
    path("get_race/", views.get_race, name="get_race"),
    path("get_event/", views.get_event, name="get_event"),
    path("get_portfolio_value/", views.get_portfolio_value, name="get_portfolio_value"),
    path("asset_price/", views.asset_price, name="asset_price"),

    path("get_notifications/", views.get_notifications, name="get_notifications"),
    path("notifications_exist/", views.notifications_exist, name="notifications_exist"),
    path("set_notification_status/", views.set_notification_status, name="set_notification_status"),

    path("get_investor_contracts/", views.get_investor_contracts, name="get_investor_contracts"),

    path("make_loan/", views.make_loan, name="make_loan"),
    path("get_loans/", views.get_loans, name="get_loans"),
    path("repay_loan/", views.repay_loan, name="repay_loan"),
    # make_loan
    # get_loans
    
]
