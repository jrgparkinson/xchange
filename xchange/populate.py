import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'xchange.settings')

import django
django.setup()

from app.models import *
from app.errors import *
from django.contrib.auth.models import User
from datetime import datetime
from django.contrib.auth.hashers import make_password
import numpy as np
import random
import pytz
import math

def populate():

    # 1. Create athletes
    # import os
    # this_file_folder = os.path.dirname(os.path.abspath(__file__))
    # with open(os.path.join(this_file_folder, 'data', 'athletes.csv'), 'r') as f:
    #     athletes = f.readlines()
    athletes = ["Jamie Parkinson", "Luke Cotter", "Miles Weatherseed", 
    "Joseph Woods", "Jack Millar", "Noah Hurton", "Oliver Paulin"]
    
    Athlete.objects.all().delete()
    for name in athletes:
        athlete = Athlete(name=name)
        athlete.save()


    # 1.5. Create events
    events = [{"name": "Cuppers", "date": datetime(year=2020, month=10, day=20,tzinfo=pytz.UTC) },
    {"name": "MK Cross Challenge", "date": datetime(year=2020, month=11, day=5, tzinfo=pytz.UTC) },
    {"name": "Varsity II-IV", "date": datetime(year=2020, month=11, day=28, tzinfo=pytz.UTC) },
    {"name": "Varsity Blues", "date": datetime(year=2020, month=12, day=6, tzinfo=pytz.UTC) },
    ]
    
    for e in events:
        event = Event(name=e["name"], date=e["date"])
        event.save()


    # 2. Create bank
    print("Create bank")
    bank = Bank(name="The Cowley Club Bank")
    bank.save()

    # 3. Create users
    print("Create users")
    users = [{"name":"jparkinson", "password": "cowleyclub", "email":"jamie.parkinson@gmail.com"},
    {"name":"lcotter", "password": "cowleyclub", "email":"luke.cotter@gmail.com"},
    {"name":"jwoods", "password": "cowleyclub", "email":"joseph.woods@gmail.com"},
    {"name":"mweatherseed", "password": "cowleyclub", "email":"speed@gmail.com"},
    {"name":"jmillar", "password": "cowleyclub", "email":"millar@gmail.com"},
    {"name":"nhurton", "password": "cowleyclub", "email":"hurtlocker@gmail.com"},
    ]

    # Clean up
    User.objects.all().delete()
    for u in users:

        user = User.objects.create(username=u["name"], password=make_password(u["password"]), is_active=True,
                                email=u["email"])
        user.save()

        # investor = Investor(user=user)
        # investor.save()

    # 4. Create shares for each athlete
    print("Create shares")
    for athlete in Athlete.objects.all():
        share = Share(athlete=athlete, volume=100, owner=bank)
        share.save()

    # 4.5 Randomly assign shares to investors
    # This is like the IPO
    # Except in the IPO, this is done via trades to the bank and 
    # hence the bank acquires money which it can loan out
    print("Assign shares to investors")

    investors = Investor.objects.all()
    for share in Share.objects.all():
        r = np.array([random.random() for i in range(len(investors))])
        r = r/np.sum(r)
        r = np.round(r, 2)

        # Create new shares of correct volume
        for i in range(len(investors)):
            share.transfer(to=investors[i], vol=r[i]*share.volume)

    # 5. Create some trades for each investor
    print('Create some trades')
    for investor in Investor.objects.all():

        # create 3 offers to sell something you own 
        for i in range(3):
            shares_for_investor = investor.get_shares_owned()

            share_to_sell = random.choice(shares_for_investor)
            if random.random() > 0.5:
                volume = share_to_sell.volume
            else:
                volume = share_to_sell.volume * random.random()
            
            share_to_sell = share_to_sell.get_vol_of_share(volume)

            trade = Trade.make_trade(commodity=share_to_sell, seller=investor, creator=investor, price=random.random())
            trade.save()


        # create 3 offers to buy from a particular investor
        all_other_shares = [s for s in Share.objects.all() if not s.owner == investor]
        for i in range(3):
            share_to_buy = random.choice(all_other_shares)

            if random.random() > 0.5:
                volume = share_to_buy.volume
            else:
                volume = share_to_buy.volume * random.random()

            share_to_buy = share_to_buy.get_vol_of_share(volume)

            trade = Trade.make_trade(commodity=share_to_buy, seller=share_to_buy.owner, buyer=investor, creator=investor, price=random.random())
            trade.save()


        # Create offers to buy a generic share
        all_athletes = Athlete.objects.all()
        for i in range(3):
            athlete_to_buy = random.choice(all_athletes)

            total_available_share_volume = athlete_to_buy.get_total_volume_of_shares()

            if random.random() > 0.5:
                volume = total_available_share_volume
            else:
                volume = total_available_share_volume * random.random()

            # Make the virtual commodity
            virtual_share = Share(athlete=athlete_to_buy, volume=volume, is_virtual=True)
            virtual_share.save()

            trade = Trade.make_trade(commodity=virtual_share, buyer=investor, creator=investor, price=random.random())
            trade.save()


    # Action some trades
    print('Action some trades')
    for investor in Investor.objects.all():

        #  Action trades where we're the seller and someone else wants to buy our stuff
        direct_trades = Trade.objects.all().filter(seller=investor).exclude(creator=investor)
        # Do something with half of them
        for t in random.choices(direct_trades, k=int(len(direct_trades)/2)):
            print(t)
            try:
                t.accept_trade(action_by=investor)
            except InsufficientShares:
                print("Insufficient shares to fulfill trade")

        # Do trades where someone offered to sell us something
        direct_trades = Trade.objects.all().filter(buyer=investor).exclude(creator=investor)
        # Do something with half of them
        for t in random.choices(direct_trades, k=int(len(direct_trades)/2)):
            print(t)
            try:
                t.accept_trade(action_by=investor)
            except InsufficientShares:
                print("Insufficient shares to fulfill trade")


        # Also open trades which we can fulfill (and which we did not create)
        open_trades = Trade.objects.all().filter(seller=None).exclude(creator=investor)
        # print("Open trades: " + str(open_trades))
        for t in random.choices(open_trades, k=math.floor(len(open_trades)/2)):
            # Can we handle this trade
            # How do we work out what this commodity is? 
            # owned_commodity = 
            # our_share_in_commodity = investor.get_share(t.commodity)
            # if our_share_in_commodity and our_share_in_commodity.volume >= commodity.volume:
                # do trade - set ourself as the seller
                
            try:
                t.seller = investor
                t.accept_trade(action_by=investor)
            except InsufficientShares:
                t.seller = None
                print("Insufficient shares to fulfill trade")

        # accept an offer to sell if possible

        # accept an offer to buy if possible


    
    # trade1 = Trade()

    # 6. Issue some dividends
    # Dividend = apps.get_model("app", "Dividend")

    # Make some loans
    # Loan = apps.get_model("app", "Loan")


    # Create some more complicated tradeables
    # Dividend = apps.get_model("app", "Dividend")



if __name__ == '__main__':
    print("Starting population script...")

    populate()