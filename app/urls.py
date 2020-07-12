from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.contrib import admin

from . import views, requests
from app.forms import UserLoginForm
from rest_framework import routers
from app import views_rest

# REST
# router = routers.DefaultRouter()
# # router.register(r'trades', views_rest.TradeViewSet)
# # router.register(r'trades', views_rest.TradeList)
# router.register(r'assets', views_rest.AssetViewSet)
# router.register(r'investors', views_rest.InvestorViewSet)
# router.register(r'entities', views_rest.EntityViewSet)
# router.register(r'banks', views_rest.BankViewSet)
# router.register(r'athletes', views_rest.AthleteViewSet)
# router.register(r'shares', views_rest.ShareViewSet)
# router.register(r'futures', views_rest.FutureViewSet)
# router.register(r'options', views_rest.OptionViewSet)
# router.register(r'clubs', views_rest.ClubViewSet)
# # router.register(r'groups', views_rest.GroupViewSet)


handler404 = views.handler404
handler500 = views.handler500
handler403 = views.handler403

urlpatterns = [
    # path('admin', admin.site.urls, name='admin'),
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

    path("get_bank_offer/", views.get_bank_offer, name="get_bank_offer"),
    path("trade_with_bank/", views.trade_with_bank, name="trade_with_bank"),
    path("get_contract/", views.get_contract, name="get_contract"),

    path("option/", views.option, name="options"),
    
    # make_loan
    # get_loans
    
    # REST
    # path('api/', include(router.urls)),
    # path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('api/trades/', views_rest.TradeList.as_view(), name="trades-list"),
    path('api/athletes/', views_rest.AthleteList.as_view(), name="athletes-list"),
    path('api/athlete/<int:pk>', views_rest.Athlete.as_view(), name="athlete"),
    path('api/entity/<int:pk>', views_rest.Entity.as_view(), name="entity"),
    path('api/entities/', views_rest.EntityList.as_view(), name="entity-list"),
    path('api/asset/<int:pk>', views_rest.AssetRetrieve.as_view(), name="asset"),
    path('api/assets/', views_rest.AssetList.as_view(), name="asset-list"),
    path('api/current_user', views_rest.current_user, name="current_user"),
    path('api/debts/', views_rest.debt_list, name='debt-list'),
    path('api/debt/<int:pk>/', views_rest.debt_detail, name='debt-detail'),

    path('api/', views_rest.api_root),
    
]

