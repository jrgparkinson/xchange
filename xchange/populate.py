import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'xchange.settings')

import django
django.setup()

from app.models import *
from app.errors import *
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.contrib.auth.hashers import make_password
import numpy as np
import random
import pytz
import math

def random_vol_of(vol):
    if random.random() > 0.5:
        return vol
    else:
        return np.round(vol * random.random(), 2)

def random_price(volume):

    return np.round(random.random() * 10 * volume, 2)

def populate():

    season = Season.objects.get_or_create(name="Preseason", start_time=datetime.now(), end_time=datetime(2020, 9, 30, 23, 59, 59))[0]
    season.save()

    # 1. Create athletes
    ouccc = Club.objects.get_or_create(name="OUCCC")[0]
    ouccc.save()

    athletes = ["Jamie Parkinson", "Luke Cotter", "Miles Weatherseed", 
    "Joseph Woods", "Jack Millar", "Noah Hurton", "Oliver Paulin"]
    # Athlete.objects.all().delete()
    for name in athletes:
        athlete = Athlete.objects.get_or_create(name=name, club=ouccc)[0]
        athlete.save()


    # # 1.5. Create events
    events = [{"name": "Varsity athletics", "date": datetime(year=2020, month=5, day=11,tzinfo=pytz.UTC), "races":[] },
    {"name": "Cuppers", "date": datetime(year=2020, month=10, day=20,tzinfo=pytz.UTC), "races":[] },
    {"name": "MK Cross Challenge", "date": datetime(year=2020, month=11, day=5, tzinfo=pytz.UTC), "races":["Senior Men", "Senior Women"] },
    {"name": "Varsity II-IV", "date": datetime(year=2020, month=11, day=28, tzinfo=pytz.UTC), "races":["Men II", "Women II", "Men III", "Men IV", "Women III"] },
    {"name": "Varsity Blues", "date": datetime(year=2020, month=12, day=6, tzinfo=pytz.UTC), "races":["Men", "Women"] },
    ]
    
    for e in events:
        event = Event.objects.get_or_create(name=e["name"], date=e["date"],season=season)[0]
        event.save()

        races = e["races"]
        for r in races:
            race = Race(name=r, event=event, time=event.date, max_dividend=20.0+random.random()*100.0)
            race.save()

            # Create results
            athletes = list(Athlete.objects.all())
            random.shuffle(athletes)
            for i in range(len(athletes)):
                result = Result(athlete=athletes[i], race=race, position=i, time=timedelta(minutes=i, seconds=random.random()*60.0))
                result.save()

    # create races
    # return

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
    {"name":"asmith", "password": "cowleyclub", "email":"smithsonian@gmail.com"},
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
        share = Share(athlete=athlete, volume=100, owner=bank,season=season)
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

            try:
                t = Trade.make_share_trade(athlete=share.athlete, volume=r[i]*share.volume, 
                creator=bank, price=random_price(r[i]*share.volume),
                seller=bank, buyer=investors[i])
                t.accept_trade(action_by=investors[i])
                t.updated = current_time() - timedelta(days=1, hours=random.random())
                t.save()
            except Exception as e:
                print("Error: " + str(e))
            # share.transfer(to=investors[i], vol=r[i]*share.volume)


    # print("====================================")
    # 5. Create some trades for each investor

    
    print('Create some trades')
    for investor in Investor.objects.all():

        # create 3 offers to sell something you own to anyone that wants it
        for i in range(3):
            shares_for_investor = investor.get_shares_owned()

            share_to_sell = random.choice(shares_for_investor)
            volume = random_vol_of(share_to_sell.volume)
            
            try:
                Trade.make_share_trade(share_to_sell.athlete, volume, creator=investor, price=random_price(volume), seller=investor)
            except XChangeException:
                pass
            


        # create 3 offers to buy from a particular investor
        all_other_shares = [s for s in Share.objects.all() if not s.owner == investor]
        for i in range(3):
            share_to_buy = random.choice(all_other_shares)

            volume = random_vol_of(share_to_buy.volume)

            try:
                Trade.make_share_trade(share_to_buy.athlete, volume, creator=investor, price=random_price(volume), buyer=investor,  seller=share_to_buy.owner)
            except XChangeException:
                pass
            


        # Create offers to buy a generic share from anyone
        all_athletes = Athlete.objects.all()
        for i in range(3):
            athlete_to_buy = random.choice(all_athletes)
            total_available_share_volume = athlete_to_buy.get_total_volume_of_shares()
            volume = random_vol_of(share_to_buy.volume)

            try:
                Trade.make_share_trade(athlete_to_buy, volume, creator=investor, price=random_price(volume), 
            buyer=investor,  seller=None)
            except XChangeException:
                pass
            

    # Action some trades
    print('Action some trades')
    # for investor in Investor.objects.all():

    #     #  Action trades where we're the seller and someone else wants to buy our stuff
    #     direct_trades = Trade.objects.all().filter(seller=investor).exclude(creator=investor)
    #     # Do something with half of them
    #     for t in random.choices(direct_trades, k=int(len(direct_trades)/2)):
    #         # print(t)
    #         try:
    #             t.accept_trade(action_by=investor)

    #         except XChangeException as e:
    #             print(e.desc)

    #     # Do trades where someone offered to sell us something
    #     direct_trades = Trade.objects.all().filter(buyer=investor).exclude(creator=investor)
    #     # Do something with half of them
    #     for t in random.choices(direct_trades, k=int(len(direct_trades)/2)):
    #         print(t)
    #         try:
    #             t.accept_trade(action_by=investor)
    #         except XChangeException as e:
    #             print(e.desc)



    #     # Also open buy trades which we can fulfill (and which we did not create)
    #     open_trades = Trade.objects.all().filter(seller=None).exclude(creator=investor)
    #     for t in random.choices(open_trades, k=math.floor(len(open_trades)/2)):
    #         try:
    #             t.seller = investor
    #             t.accept_trade(action_by=investor)
    #         except XChangeException as e:
    #             t.seller=None
    #             print(e.desc)


    #     # Open sell trades that we want to buy
    #     open_trades = Trade.objects.all().filter(buyer=None).exclude(creator=investor)
    #     for t in random.choices(open_trades, k=math.floor(len(open_trades)/2)):
    #         try:
    #             t.buyer = investor
    #             t.accept_trade(action_by=investor)
    #         except InsufficientShares:
    #             t.buyer = None
    #             print("Insufficient shares to fulfill trade")
    #         except InsufficientFunds:
    #             t.buyer = None
    #             print("Insufficient funds")
    #         except XChangeException as e:
    #             t.buyer = None
    #             print(e.desc)



    
    # trade1 = Trade()
    # 
    

    # 6. Issue some dividends
    # print("Before dividends, capital: ")
    # for i in Investor.objects.all():
    #     print(i)

    # for event in Event.objects.all():

    #     # This should be done every hour by a scheduled job
    #     make_share_snapshots(event)


    #     for athlete in Athlete.objects.all():
    #         val = random_price(volume)
    #         div = Dividend(event=event, athlete=athlete, ammount=val)
    #         div.save()

    #         # Need to write this
    #         distribute_dividends(event)

    # print("After dividends, capital: ")
    # for i in Investor.objects.all():
    #     print(i)

    # Make some loans
    # for i in Investor.objects.all():
    #     loan_ammount = random.random()*100.0
    #     interest = 0.02

    #     interval = timedelta(seconds=3)

    #     loan = Loan.create_loan(bank, i, interest, loan_ammount, interval)
        
    # print("After loans, capital: ")
    # for i in Investor.objects.all():
    #     print(i)
    
    # import time
    # for step in range(25):
    #     time.sleep(1)
    #     print("Checking for loan repayments")
    #     pay_all_loans()

    # print("After repayments, capital: ")
    # for i in Investor.objects.all():
    #     print(i)
    


    # Create some more complicated tradeables
    



if __name__ == '__main__':
    print("Starting population script...")

    populate()