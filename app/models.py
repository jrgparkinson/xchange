from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from datetime import timedelta, datetime
import time
import pytz
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1' # fix for server
import numpy as np
from app.errors import *
from django.db.models import Q
from django.contrib import admin  # .admin.ModelAdmin import message_user
import re
from background_task import background
# from background_task.models import BackgroundTask
from django.db.models.signals import pre_save
import logging
from typing import List
import json
import decimal
from rest_framework.exceptions import APIException

# Get an instance of a logger
logger = logging.getLogger(__name__)

class Season(models.Model):

    OPEN = "O"
    SUSPENDED = "S"
    FINISHED = "F"
    STATUS_CHOICES = (
        (OPEN, "Open"),
        (SUSPENDED, "Suspended"),
        (FINISHED, "Finished"),
    )

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=OPEN)
    name = models.CharField(max_length=100)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    def __str__(self):
        return "{}: {} - {} ({})".format(self.name, 
        self.start_time.strftime("%m/%d/%Y, %H:%M:%S"), 
        self.end_time.strftime("%m/%d/%Y, %H:%M:%S"), 
        self.print_status)

    def serialize(self):
        return {"id": self.pk,
        "name": self.name,
        "start": self.start_time,
        "end": self.end_time,
        "status": self.print_status}

    @property
    def print_status(self):
        return dict(self.STATUS_CHOICES)[self.status]

def current_time():
    return datetime.now(pytz.utc)


def get_current_season():
    """ Should only ever be one season that is 'open' """
    return Season.objects.get(status=Season.OPEN)


def format_currency(currency):
    locale.setlocale(locale.LC_ALL, "")
    currency_str = locale.currency(currency, grouping=True) + "M"
    return currency_str


def round_time(time, interval="seconds"):
    """ Round to nearest interval as specified """
    if interval == "seconds":
        time = time.replace(microsecond=0)

    return time


class Entity(models.Model):
    INITIAL_CAPITAL = 1000
    capital = models.DecimalField(max_digits=10, decimal_places=2, default=INITIAL_CAPITAL)

    def serialize(self):
        s = {"capital": self.capital}

        s["share_value"] = self.share_value
        s["total_value"] = self.total_value

        return s

    def get_capital(self, time):
        current_capital = self.capital

        # Transactions for this entity
        cash_transactions = TransactionHistory.objects.all().filter(
            (Q(sender=self) | Q(recipient=self)) & Q(timestamp__gte=time)& Q(season=get_current_season())
        )

        # Add/remove cash to get back to point in time we care about
        for t in cash_transactions:
            if t.sender == self:
                current_capital = current_capital + t.ammount

            else:
                current_capital = current_capital - t.ammount

        return current_capital

    def get_portfolio_values(self):
        cash_transactions = (
            TransactionHistory.objects.all()
            .filter((Q(sender=self) | Q(recipient=self)) & Q(season=get_current_season()))
            .order_by("timestamp")
        )
        this_time = current_time()
        # cash_transactions = sorted(cash_tra)

        # Start of the season
        investor_capital = self.INITIAL_CAPITAL
        cash_positions = [
            {
                "time": round_time(get_current_season().start_time),
                "value": investor_capital,
                "type": "cash",
            }
        ]

        times = [datetime.now()]

        for t in cash_transactions:

            # If this investor sent the money, then return state to before this (add money)
            # if t.sender == self:
            #     investor_capital = investor_capital - t.ammount
            # else:
            #     investor_capital = investor_capital + t.ammount

            investor_capital = t.capital_for(self)
            cash_positions.append(
                {
                    "time": round_time(t.timestamp),
                    "value":investor_capital,
                    "type": "cash",
                }
            )

        if not self.capital == investor_capital:
            logger.info(
                "ERROR computing capital! {} != {}".format(
                    self.capital, investor_capital
                )
            )
            # raise XChangeException("Internal inconsistency in determing cash content of portfolio value")

        cash_positions.append(
            {"time": round_time(this_time), "value": self.capital, "type": "cash"}
        )
        times.append(datetime.now())


        # # Assume everyone starts with 0 shares
        share_positions = [
            {
                "time": round_time(get_current_season().start_time),
                "value": 0.0,
                "type": "share",
            }
        ]

        # Now redo with share ownership
        shares_owned = ShareOwnership.objects.all().filter(entity=self).order_by('timestamp')
        logger.info("Processing {} shares owned".format(len(shares_owned)))
        
        # Construct athlete values so we don't have to keep querying it
        trades = Trade.objects.all().filter(Q(status=Trade.ACCEPTED) & Q(season=get_current_season())).order_by('updated')

        all_athletes = Athlete.objects.all()
        athlete_vals = {}
        for a in all_athletes:
            athlete_trades = trades.filter(Q(asset__share__athlete=a))
            athlete_vals[a.id] = [[t.updated, t.price/t.asset.share.volume if t.asset.share.volume else 0] for t in athlete_trades]


        # This loop is slow, timing to work out how we can speed it up
        time_loads = 0
        time_athletes = 0
        time_val = 0
        for share in shares_owned:
            a = datetime.now()
            athletes = json.loads(share.share_vol_owned)
            time_loads = time_loads + (datetime.now()-a).total_seconds()

            total_share_val = 0
            for athlete_id, vol in athletes.items():
                a = datetime.now()
                athlete = Athlete.objects.get(id=int(athlete_id)) # type: Athlete
                time_athletes = time_athletes + (datetime.now()-a).total_seconds()

                a = datetime.now()


                # val = athlete.get_value(time=share.timestamp)
                ath_vals = athlete_vals[int(athlete_id)]
                vals_before_time = list(filter(lambda t: t[0] <= share.timestamp, ath_vals))
                val = vals_before_time[-1][1] if vals_before_time else 0

                time_val = time_val + (datetime.now()-a).total_seconds()

                total_share_val = total_share_val + float(val)*float(vol)

            share_positions.append(
                {
                    "time": round_time(share.timestamp),
                    "value": total_share_val,
                    "type": "share",
                }
            )

        share_positions.append(
            {"time": round_time(this_time), "value": total_share_val, "type": "share"}
        )

        times.append(datetime.now())
        logger.info(f"Got shares, {time_loads}, {time_athletes}, {time_val}")
        
        # Now do derivatives. Recalculate this after every trade
        # As share trades affect derivative pricing
        # again, assume everyone starts with 0 derivatives

        asset_transactions = (
            Trade.objects.all().filter(status=Trade.ACCEPTED).order_by("updated")
        )
        derivative_transactions = [t for t in asset_transactions] #  if t.asset.is_derivative()
        derivatives = [{"time": round_time(get_current_season().start_time), "value": 0.0, "type": "derivative"}]
    # 
        for t in derivative_transactions:
            derivatives_owned = self.get_contracts_held(t.updated)
            derivatives_value = np.sum(np.array([d.value for d in derivatives_owned]))
            derivatives.append({"time": round_time(t.updated), "value": derivatives_value, "type": "derivative"})

        derivatives.append({"time": round_time(this_time), "value": derivatives_value, "type": "derivative"})

        # Now the trick is to combine them
        # all_positions = share_positions + cash_positions + derivatives
        all_positions = sorted(
            share_positions + cash_positions + derivatives, key=lambda t: t["time"]
        )
        # logger.info(all_positions)
        times.append(datetime.now())

        # all_positions_merged = []
        records_expected_per_time = {}
        records_processed_per_time = {}
        for time in list(set([t["time"] for t in all_positions])):
            all_for_time = [t for t in all_positions if t["time"] == time]
            # logger.info("Found {} records for time = {}".format(len(all_for_time), time))
            records_expected_per_time[time.timestamp()] = len(all_for_time)
            records_processed_per_time[time.timestamp()] = 0

        combined_total = []
        running_cash = 0
        running_shares = 0
        running_derivs = 0
        for t in all_positions:
            if t["type"] == "cash":
                running_cash = t["value"]
            elif t["type"] == "share":
                running_shares = t["value"]
            elif t["type"] == "derivative":
                running_derivs = t["value"]

            records_processed_per_time[t["time"].timestamp()] = (
                records_processed_per_time[t["time"].timestamp()] + 1
            )
            if (
                records_processed_per_time[t["time"].timestamp()]
                == records_expected_per_time[t["time"].timestamp()]
            ):
                combined_total.append(
                    {"time": t["time"], "value": float(running_cash) + float(running_shares) + float(running_derivs)}
                )
        times.append(datetime.now())

        logger.info("Timing: " + str([(t - times[0]).total_seconds() for t in times] ) )
        return_vals = {
            "combined": combined_total,
            "cash": cash_positions,
            "shares": share_positions,
            "derivatives": derivatives,
        } 
        # logger.info(return_vals)

        return return_vals # cash_positions

    def get_contracts_held(self, timestamp=None):
        """ Get all contracts held by this entity at some date/time """
        if not timestamp:
            timestamp = current_time()

        # Get active contracts
        # contracts = Contract.objects.all().filter(Q(status=Contract.ACTIVE))
        futures = Future.objects.all().filter(Q(status=Contract.ACTIVE) & (Q(buyer=self) | Q(seller=self)))
        options = Option.objects.all().filter(Q(status=Contract.ACTIVE) & (Q(buyer=self) | Q(seller=self)))
        owned_contracts = list(futures) + list(options)
        # for c in contracts:
                # 
            # relevant_history = ContractHistory.objects.all().filter(Q(contract=c) & Q(timestamp__lte=timestamp))
            # relevant_history = relevant_history.order_by('-timestamp')

            # if len(relevant_history) > 0:
            #     most_recent = relevant_history[0]
            #     if most_recent.owner == self or most_recent.other_party == self:
            #         owned_contracts.append(c)

        return owned_contracts

    def get_shares_wealth(self) ->float:
        """ Get entities current share holding value """
        shares = self.get_shares_owned()
        wealth = 0
        for s in shares:
            wealth = wealth + float(s.volume) * s.athlete.get_value()

        # logger.info("Wealth: " + str(wealth))

        return float(wealth)

    @property
    def share_value(self):
        return self.get_shares_wealth()

    @property
    def total_value(self):
        return self.share_value + float(self.capital)

    @property
    def derivatives_value(self):
        return 0.0

    def get_share_vol(self, athlete, time):
        current_shares = self.shares_in_athlete(athlete)

        vol = 0
        if current_shares:
            vol = current_shares.volume

        trades = Trade.objects.all().filter(
            (Q(buyer=self) | Q(seller=self))
            & Q(status=Trade.ACCEPTED)
            & Q(updated_gte=time)
            & Q(season=get_current_season())
        )
        trades = [t for t in trades if t.is_share()]

        for t in trades:
            if t.buyer == self:
                vol = vol + t.asset.volume
            else:
                vol = vol + t.asset.volume

        return vol

    def can_sell_asset(self, asset):
        if asset.is_share():
            owned_shares = self.shares_in_athlete(asset.share.athlete)
            if owned_shares and owned_shares.volume >= asset.share.volume:
                return True

            return False

        else:
            return False

    def get_shares_owned(self) -> List['Share']:
        shares = Share.objects.filter(owner=self, is_virtual=False, season=get_current_season())
        return shares

    def shares_in_athlete(self, athlete):
        try:
            share = Share.objects.get(owner=self, is_virtual=False, athlete=athlete, season=get_current_season())
            return share
        except Share.DoesNotExist:
            return None

    def saleable_shares_in_athlete(self, athlete):
        # If we introduce futures/options, will need to consider them here
        # as you may own shares in an athlete but not be able to sell them as they're under contract
        return self.shares_in_athlete(athlete)

        # Below happens if we've messed up and made multiple shares for one investor/athlete pair
        # except Share.MultipleObjectsReturned:
        # shares = Share.objects.filter(owner=self, is_virtual=False, athlete=athlete)
        # logger.info("Shares for {}: {}".format(self, str(shares)))
        # return None

    def get_share(self, share):
        try:
            share = Share.objects.get(
                owner=self, is_virtual=False, athlete=share.athlete, season=get_current_season()
            )
            return share
        except Share.DoesNotExist:
            return None

    def transfer_cash_to(self, ammount, to, reason):
        """ Transfer cash from this entity to another
        """
        if self.capital < ammount:
            raise InsufficientFunds(
                "Capital ({}) is less than the transfer ammount ({})".format(
                    self.capital, ammount
                )
            )

        ammount = decimal.Decimal(ammount)
        self.capital = self.capital - ammount
        to.capital = to.capital + ammount

        
        self.save()
        to.save()

        trans = TransactionHistory(
            sender=self, recipient=to, ammount=ammount, reason=reason, season=get_current_season()
        )
        trans.save()

    def is_investor(self):
        try:
            i = self.investor
            return True
        except Investor.DoesNotExist:
            return False

    @property
    def print_name(self):
        if self.is_investor():
            return self.investor.display_name
        else:
            return self.bank.name

    @property
    def portfolio(self):
        shares_owned = [{"athlete_id": s.athlete.id, "volume": s.volume } for s in self.get_shares_owned()]
        contracts = [c.id for c in self.get_contracts_held()]

        return {"summary": {"capital": self.capital,
                "shares": self.share_value,
                "derivatives": self.derivatives_value},
                "shares": shares_owned,
                "contracts": contracts }


    # @property
    # def name(self):
    #     return self.print_name

    @property
    def to_html(self):
        if self.is_investor():
            return '<span class="badgeContainer"><a href="' + settings.DEPLOY_URL + 'investor/' + str(self.id) + '" class="badge badge-primary">' + self.investor.display_name + '</a></span>'
        else:
            return self.bank.name

    def is_bank(self):
        try:
            b = self.bank
            return True
        except Bank.DoesNotExist:
            return False
        except Exception:
            return False

    def __str__(self):
        if self.is_investor():
            return self.investor.__str__()
        elif self.is_bank():
            return self.bank.__str__()
        else:
            return "Unknown entity with id {}".format(self.id)

    # Override equality operator as a Bank with pk 2 = an Entity with pk 2
    def __eq__(self, other):
        if not (
            isinstance(other, Entity)
            or isinstance(other, Investor)
            or isinstance(other, Bank)
        ):
            return False

        if self.pk is None:
            return self is other

        return self.pk == other.pk


class Bank(Entity):
    """ A bank can offer loans """

    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    def serialize(self):
        return {"name": self.name, "capital": self.capital}

    def get_buy_sell_offer(self, athlete_id, volume):
        """ What will bank buy/sell for """
        athlete = Athlete.objects.get(pk=athlete_id)
        current_price = athlete.get_value()
        all_shares = Share.objects.all().filter(athlete=athlete, is_virtual=False)
        total_vol = np.sum([s.volume for s in all_shares])

        bank_shares = self.shares_in_athlete(athlete)

        # if not bank_shares:
        #     return None

        bank_vol = bank_shares.volume if bank_shares else 0      

        # Price increases by 1% for each 1% of total share vol
        sell_price_per_unit = decimal.Decimal(current_price*1.05)
        buy_price_per_unit = decimal.Decimal(current_price*0.95)

        total_sell_price = 0
        total_buy_price = 0

        remaining_vol = decimal.Decimal(volume)
        share_division =  decimal.Decimal(0.01)*decimal.Decimal(total_vol)
        while remaining_vol > 0.0:
            this_vol = min(share_division, remaining_vol)
            total_sell_price = total_sell_price + (sell_price_per_unit * this_vol)
            total_buy_price = total_buy_price + (buy_price_per_unit * this_vol)

            remaining_vol = remaining_vol - this_vol
            sell_price_per_unit = sell_price_per_unit * decimal.Decimal(1.01)
            buy_price_per_unit = buy_price_per_unit * decimal.Decimal(0.99)

        if volume > bank_vol:
            total_sell_price = -1

        if total_buy_price > self.capital:
            total_buy_price = -1

        # logger.info("Season: {}".format(get_current_season()))
        offer = BankOffer(athlete=athlete, volume=volume, total_sell_price=total_sell_price, 
                            total_buy_price=total_buy_price, 
                            bank=self, season=get_current_season())
        offer.save()
        return offer

def get_bank() -> Bank:
    return Bank.objects.get(name='The Cowley Club Bank')


class Investor(Entity):
    """
    An investor is an individual who trades stuff
    """

    DEFAULT = "N" # N for no preference
    LIGHT = "L"
    DARK = "D"
    OXFORD = "O"
    CAMBRIDGE = "C"
    THEMES = (
        (DEFAULT, "Browser default"),
        (LIGHT, "Light"),
        (DARK, "Dark"),
        (OXFORD, "Oxford"),
        (CAMBRIDGE, "Cambridge"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    uitheme = models.CharField(max_length=1, choices=THEMES, default=LIGHT)

    def __str__(self):
        return "{}".format(self.display_name)

    def __repr__(self):
        return self.display_name

    def print_uitheme(self):
        return dict(Investor.THEMES)[self.uitheme]

    @property
    def name(self):
        return self.display_name

    @property
    def display_name(self):
        if self.user.first_name:
            name = self.user.first_name
            if self.user.last_name:
                name = name + " " + self.user.last_name
        else:
            return self.user.username

    def serialize(self):
        # return {}
        return {"id": self.pk, "name": self.display_name, "capital": self.capital}


# This is a quicker way of serializing an entity
def serialize_entity(entity: Entity):
    if not entity:
        return None
    if entity.is_investor():
        return entity.investor.serialize()
    elif entity.is_bank():
        return entity.bank.serialize()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Investor.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.investor.save()


class Club(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Athlete(models.Model):
    """
    An athlete who earns dividends for their share holders
    """

    VALUE_AVERAGE_SIZE = 3

    name = models.CharField(max_length=100, unique=True)
    power_of_10 = models.URLField()
    club = models.ForeignKey(Club, on_delete=models.CASCADE)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name

    @property
    def to_html(self):
        return '<span class="badgeContainer"><a href="/athlete/' + str(self.id) + '" class="badge badge-danger">' + self.name + '</a></span>'

    def serialize(self, investor: Investor =None):
        s = {"id": self.pk, "name": self.name, "value": self.get_value()}

        if investor:
            shares = investor.saleable_shares_in_athlete(self)
            vol = 0
            if shares:
                vol = shares.volume
            s["vol_owned"] = vol

        return s

    def get_vol_owned_by(self, investor: Investor):
        shares = investor.saleable_shares_in_athlete(self)
        vol = 0
        if shares:
            vol = shares.volume
        return vol

    def get_all_trades(self):
        trades = (
            Trade.objects.all()
            .filter(asset__share__athlete=self, status=Trade.ACCEPTED, season=get_current_season())
            .order_by("updated")
        )
        return trades

    @property
    def historical_values(self):
        return self.get_historical_value()

    def get_historical_value(self):
        # Worried this retrieve might end up being very slow
        # trades = Trade.objects.all().filter(status=Trade.ACCEPTED).order_by('updated')
        trades = self.get_all_trades()
        # trades = [t for t in trades if t.asset.is_share() and t.asset.share.athlete == self]

        logger.info("Found {} trades for athlete".format(len(trades)))
        
        values = [
            {"time": t.updated, "value": t.price / t.asset.share.volume} for t in trades
        ]

        # logger.info(values)
        return values

    def compute_value_from_trades(trades):
        # note that t.price is the price for the full volume,
        # to t.price = price per volume * volume
        average = np.sum(np.array([t.price for t in trades])) / np.sum(
            np.array([t.asset.share.volume for t in trades])
        )

        # Just use most recent trade
        trades = sorted(trades, key=lambda t: t.updated, reverse=True)
        for t in trades:
            logger.info("Trade on {}".format(t.updated))
        trade = trades[0]
        value = trade.price / trade.asset.share.volume
        # logger.info("Most recent data: {}".format(trade.updated))

        return value

    def get_value(self, time=None) -> float:
        """ Get value of this athlete at some point in time """
        if not time:
            time = current_time()
        # Get all trades for this athlete before this time which were accepted
        trades = Trade.objects.all().filter(
            Q(asset__share__athlete=self) & Q(status=Trade.ACCEPTED) & Q(season=get_current_season())
            & Q(updated__lte=time)
        ).order_by('-updated')[:1]
        # Also filter and sort by time
        # trades = sorted(
        #     [t for t in trades if t.updated <= time],
        #     key=lambda t: t.updated,
        #     reverse=True,
        # )  # more recent dates at the front

        if len(trades) == 0:
            return np.nan

        latest_trade = trades[0]

        # Volume weighted average
        # av = Athlete.compute_value_from_trades(trades)
        # logger.info("Average of {} trades = {}".format(len(trades), av))
        vol = latest_trade.asset.share.volume
        if vol == 0:
            # if latest_trade.price != 0.0:
            #     logger.info("Warning! Trade with 0 volume: {}".format(latest_trade))
            value = 0
        else:
            value = latest_trade.price / vol
        return float(value)

    def get_total_volume_of_shares(self):
        shares = Share.objects.filter(athlete=self, season=get_current_season())
        volume = np.sum(np.array([float(s.volume) for s in shares]))
        # volume = np.round(volume, 2)
        return volume


class ShareIndexValue(models.Model):
    athletes = models.ManyToManyField(to=Athlete)
    value = models.FloatField()
    date = models.DateTimeField(auto_now_add=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    TOP10 = "T"
    TYPE_CHOICES = ((TOP10, "Top 10"),)

    index_type = models.CharField(max_length=1, choices=TYPE_CHOICES, default=TOP10)

    @property
    def daily_change(self):
        return ShareIndexValue.get_daily_change(self.index_type)

    @staticmethod
    def compute_value(index_type):
        if index_type == ShareIndexValue.TOP10:
            # TODO: compute top 10 index and save value

            # value = random.random()
            athletes = Athlete.objects.all()
            athletes = sorted(athletes, key=lambda a: a.get_value(), reverse=True)
            if len(athletes) > 10:
                athletes = athletes[:10]

            value = np.mean(np.array([a.get_value() for a in athletes]))

            try:
                t = ShareIndexValue(value=value, season=get_current_season())
                t.save()
                t.athletes.add(*athletes)
                t.save()
            except Exception as e:
                logger.warning(traceback.print_tb(e.__traceback__))
                logger.info("Unable to make shareIndexValue for value: {}".format(value))

        else:
            raise XChangeException("Unknown index type " + str(index_type))

    @staticmethod
    def get_value(index_type):
        """ Get latest value of the index """
        values = (
            ShareIndexValue.objects.all()
            .filter(index_type=index_type,season=get_current_season())
            .order_by("-date")
        )
        if len(values) > 0:
            return values[0]
        else:
            return np.nan

    @staticmethod
    def get_daily_change(index_type):
        """ Get % change in index value since 24 hours ago """
        current_value = ShareIndexValue.get_value(index_type).value

        one_day_ago = current_time() - timedelta(days=1.0)
        previous_values = (
            ShareIndexValue.objects.all()
            .filter(Q(index_type=index_type) & Q(date__lte=one_day_ago) & Q(season=get_current_season()))
            .order_by("-date")
        )
        if len(previous_values) > 0:
            prev_val = previous_values[0].value
        else:
            logger.info("No index data to compare against")
            return np.nan

        change = 100.0 * (current_value - prev_val) / prev_val
        logger.info("Change: {}".format(change))
        return change


class Asset(models.Model):
    """
    Something that can be bought and sold
    A virtual asset is one involved in an open trade
    
    The owner can be null if it is a virtual asset
    
    """

    is_virtual = models.BooleanField(
        default=False
    )  # need ability to create virtual commodities for an open buy trade
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def serialize(self):
        if self.is_share():
            return self.share.serialize()
        elif self.is_option():
            return self.contract.future.option.serialize()
        elif self.is_future():
            return self.contract.future.serialize()
        elif self.is_swap():
            return self.contract.swap.serialize()
        else:
            logger.info("Trying to serialize unknown asset type!")
            logger.info(self)
            return {"is_virtual": self.is_virtual}

    def is_share(self):
        try:
            share = self.share
        except Share.DoesNotExist:
            return False
        except Exception:
            logger.warning(traceback.print_tb(e.__traceback__))
            return False
        return True

    def is_contract(self):
        try:
            c = self.contract
        except Contract.DoesNotExist:
            return False
        return True

    def is_future(self):
        if not self.is_contract():
            return False
        try:
            c = self.contract.future

            try:
                # Check it's not actually an option
                f = c.option
                return False
            except Option.DoesNotExist:
                pass
        except Future.DoesNotExist:
            return False

        return True

    def is_derivative(self):
        return self.is_contract()

    def is_swap(self):
        if not self.is_contract():
            return False

        try:
            x = self.contract.swap
        except Swap.DoesNotExist:
            return False
        return True

    def is_option(self):
        if not self.is_contract():
            return False
        try:
            f = self.contract.future.option
        except Option.DoesNotExist:
            return False
        except Future.DoesNotExist:
            return False
        return True

    @property
    def asset_type(self):
        if self.is_share():
            return "Share"
        elif self.is_future():
            return "Future"
        elif self.is_option():
            return "Option"
        elif self.is_swap():
            return "Swap"
        else:
            return "Unknown asset type"

    def __str__(self):
        if self.is_share():
            return self.share.__str__()
        elif self.is_future():
            return self.contract.future.__str__()
        else:
           return "Asset. Virtual: {}".format(self.is_virtual)


class Share(Asset):
    """
    Most common type of asset - a share in an athlete
    """

    owner = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_owner",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    athlete = models.ForeignKey(
        Athlete,
        related_name="%(app_label)s_%(class)s_athlete",
        on_delete=models.CASCADE,
    )
    volume = models.DecimalField(max_digits=10, decimal_places=2)

    def __repr__(self):
        return "{}: {}".format(str(self.athlete), self.volume)

    def __str__(self):
        val = "{}: {}".format(str(self.athlete), self.volume)
        if self.is_virtual:
            val = val + " (virtual)"
        else:
            val = val + " (real)"

        return val

    def serialize(self):
        return {
            "id": self.pk,
            "owner": self.owner,
            "virtual": self.is_virtual,
            "athlete": self.athlete.serialize(),
            "volume": self.volume,
        }

    def transfer(self, to: Entity, vol: float):

        new_share = self.get_vol_of_share(vol)

        if not new_share:
            return False
        else:

            existing_share = to.shares_in_athlete(new_share.athlete)

            if existing_share:
                existing_share.volume = existing_share.volume + new_share.volume
                existing_share.save()
                new_share.delete()

            else:
                new_share.owner = to
                new_share.save()

            return True

    def get_vol_of_share(self, vol):
        if vol > self.volume:
            return False

        if vol == self.volume:
            return self

        else:
            self.volume = self.volume - vol
            self.save()
            new_share = Share(
                athlete=self.athlete, volume=vol, owner=self.owner, season=self.season
            )
            new_share.save()
            return new_share


class Contract(Asset):
    """ 
    A contract is a type of asset which is a contract between two parties.

    This is an abstract class. 
    """

    UNSOLD = "U"
    ACTIVE = "A"
    SETTLED = "S"
    VOID = "V"
    STATUSES = (
        (UNSOLD, "Unsold"),
        (ACTIVE, "Active"),
        (SETTLED, "Settled"),
        (VOID, "Void")
    )

    status = models.CharField(max_length=1, choices=STATUSES, default=UNSOLD)

    def serialize(self):
        return {"id": self.id,
                "status": self.status}

    def __str__(self):
        return "{} contract. Status: {}".format(self.contract_type, self.status)
    
    @property
    def long_pretty_print(self):
        raise XChangeException("Contract.long_pretty_print not implemented")

    @property
    def value(self):
        """ This should be overriden """
        raise XChangeException("Contract.value not implemented")

    @property
    def contract_type(self):
        return self.asset_type

    def get_obligation(self, investor):
        raise XChangeException("Contract.get_obligation not implemented")

    def get_other_party_to(self, investor):
        raise XChangeException("Contract.get_other_party_to not implemented")

class Future(Contract):
    """ An agreement to buy/sell in the future at a fixed price """

    # Total price of future
    strike_price = models.DecimalField(max_digits=10, decimal_places=2)
    strike_time = models.DateTimeField()

    # Assume underlying asset is a share for now - otherwise this gets very complicated
    underlying_asset = models.ForeignKey(Share, on_delete=models.CASCADE)

    SELL = "S"
    BUY = "B"
    NONE = "N"
    OBLIGATIONS = (
        (BUY, "Buy"),
        (SELL, "Sell"),
        (NONE, "None"),
    )

    # Who will buy the underlying asset
    buyer = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_buyer",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    # Who will sell the underlying asset
    seller = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_seller",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    def __str__(self):
        return "Future: {} to buy ({}, {}) from {} for {} at {}".format(self.buyer,
        self.underlying_asset.athlete.name,
        self.underlying_asset.volume, self.seller, self.strike_price, self.strike_time)

    def serialize(self):
        s = {"id": self.pk,
            "underlying": self.underlying_asset.serialize(),
            "strike_price": self.strike_price,
            "strike_date": self.strike_time,
            "status": self.status,
            "buyer": serialize_entity(self.buyer),
            "seller": serialize_entity(self.seller),
            "type": "Future",
        }

        return s

    def get_other_party_to(self, investor):
        if self.buyer == investor:
            return self.seller
        elif self.seller == investor:
            return self.buyer
        else:
            raise XChangeException("Investor not involved in contract")


    def get_obligation(self, investor):
        if self.buyer == investor:
            return Future.BUY
        elif self.seller == investor:
            return Future.SELL
        else:
            return Future.NONE
            # raise XChangeException("Investor not involved in contract")

    @property
    def long_pretty_print(self):
        asset = "{} to buy {} shares of {} for {} at {}".format(self.buyer.print_name, 
                                                        self.underlying_asset.volume, 
                                                        self.underlying_asset.athlete.name, 
                                                        self.strike_price, self.strike_time)
        text = "Futures contract: " + asset
        text = text + " (current value: {:.2f})".format(self.value)
        return text

    @property
    def strike_price_per_volume(self):
        return self.strike_price/self.underlying_asset.volume

    @property
    def value(self):
        """ value of futures contract is strike_price - current_price 
        TODO 
        """
        current_price_per_share = self.underlying_asset.athlete.get_value()
        current_price = current_price_per_share*float(self.underlying_asset.volume)

        logging.info("Current price: {} ({} per share, vol={}) for future id: {}".format(current_price, current_price_per_share, self.underlying_asset.volume, self.id))
        return current_price - float(self.strike_price)
       
    def execute(self):
        """ Called when the strike date is reached """

    def get_relevant_trade(self):
        """ The relevant trade is the most recent accepted trade (or pending if only one)
        for this future. It determines who the buyers and sellers are """
        # First look for completed trades
        trades = Trade.objects.all().filter(Q(season=get_current_season()) & Q(asset__future=self) & Q(status=Trade.ACCEPTED)).order_by('-updated')
        if trades:
            return trades[0]

        else:
            # Now look for pending trades
            trades = Trade.objects.all().filter(Q(season=get_current_season()) & Q(asset__future=self) & Q(status=Trade.PENDING)).order_by('-updated')

            if trades:
                return trades[0]

        # If we didn't find anything
        return None


class ContractHistory(models.Model):
    """ To keep track of who was engaged in a contract at some point in time 
    Created once a futures contract is traded, and updated whenver it is traded again """
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    party_a = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_owner",
        on_delete=models.CASCADE,
    )
    party_b = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_other_party",
        on_delete=models.CASCADE,
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{} contract between {} and {} ({})".format(self.contract.contract_type, 
               self.party_a.print_name, self.party_b.print_name, self.timestamp)


class Option(Future):
    """ An option is a future where one party has the option to go through with the trade or not """

    # Note that banks cannot hold options, only investors
    # option_holder = models.ForeignKey(Investor, related_name="%(app_label)s_%(class)s_option_holder", on_delete=models.CASCADE)
    # option holder is just the owner
    current_option = models.BooleanField(default=True)

    option_holder = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_option_holder",
        on_delete=models.CASCADE,
        blank=True,
        null=True
    )

    def serialize(self):
        s = super().serialize()

        s["type"] = "Option"
        s["current_option"] = self.current_option,
        s["option_holder"] = serialize_entity(self.option_holder)
        
        return s

@background(schedule=0)
def settle_future(future_id):
    """ To call:
    settle_future(future, schedule=future.strike_time)
    """

    logging.info("Settle future with id: {}".format(future_id))
    future = Future.objects.get(pk=future_id) # type: Future
    settle_future_now(future)

def settle_future_now(future: Future):
    if not future.status == Contract.ACTIVE:
        logging.info("Future not active, cannot be settled")
        return

    if future.is_option() and not future.option.current_option:
        logging.info("Option is to not transfer assets")
        future.status = Contract.SETTLED
        future.save()
        return

    if not (future.seller and future.buyer):
        raise XChangeException("Future cannot be settled - does not have buyer and seller")

    # Now we try and transfer the underlying asset
    # What to do if one party doesn't have the shares or cash to fulfill deal?
    # Abort - one or both parties default, and owe a debt of the 2*future value

    seller_has_shares =  future.seller.can_sell_asset(future.underlying_asset)
    buyer_has_cash = future.buyer.capital >= future.strike_price

    if seller_has_shares and buyer_has_cash:
        
        # Do the transfer by creating and immediately accepting a share trade
        vol = future.underlying_asset.volume
        t = Trade.make_share_trade(future.underlying_asset.athlete, vol, future.seller, 
                                    future.strike_price, future.seller, future.buyer)
        t.accept_trade(action_by=future.buyer, skip_notif=True)

        future.status = Contract.SETTLED
        future.save()

        # Send notifications
        common = "{:.2f} shares in {} for {:.2f} per share".format(vol, 
        future.underlying_asset.athlete.name, future.strike_price/vol)
        
        Notification.send_notification(title="Future contract settled", 
                                        description="You bought " + common, entity=future.buyer)
        Notification.send_notification(title="Future contract settled", 
                                        description="You sold" + common, entity=future.seller)
        
    else:

        logger.info(f"Seller has shares: {seller_has_shares}, buyer cash: {buyer_has_cash}")
        seller_shares = future.seller.shares_in_athlete(future.underlying_asset.share.athlete)
        seller_vol = seller_shares.volume if seller_shares else 0
        logger.info(f"Seller ({future.seller}) shares: {seller_shares}")

        # if neither party can fulfill obligation, contract is void
        if not seller_has_shares and not buyer_has_cash:
            future.status = Contract.VOID
            future.save()

            desc = "Future contract between {} and {} for {} void as neither party can fulfill obligation".format(buyer, seller, common)
            Notification.send_notification(title="Future contract void", description=desc, entity=buyer)
            Notification.send_notification(title="Future contract void", description=desc, entity=seller)
        
        else:
            # Work out value of contract,
            # defaulter owes this x 1.5
            # pays what they can, the bank pays the rest, then they owe the bank a debt
            val = future.value
            
            defaulter = None # type: Entity
            non_defaulter = None # type: Entity
            if seller_has_shares and not buyer_has_cash:
                defaulter = future.buyer
                non_defaulter = future.seller
            else:
                defaulter = future.seller
                non_defaulter = future.buyer

            # contract value is athlete value - strike price
            # so if the value of the contract is positive, the buyer is getting a good deal
            # and if it is negative, the seller is getting a good deal
            if (val > 0 and defaulter == future.buyer) or (val < 0 and defaulter==future.seller):
                # here, the defaulter was due to benefit so we should do nothing
                future.status = Contract.VOID

                if defaulter == future.buyer:
                    desc = "Future contract between {} and {} for {} void as buyer cannot fulfill obligation but was due to benefit".format(buyer, seller, common)
                else:
                    desc = "Future contract between {} and {} for {} void as seller cannot fulfill obligation but was due to benefit".format(buyer, seller, common)
                
                Notification.send_notification(title="Future contract void", description=desc, entity=buyer)
                Notification.send_notification(title="Future contract void", description=desc, entity=seller)

            else:
                val_owed = decimal.Decimal(np.round(val*1.5, 2))

                val_payable = defaulter.capital
                debt = val_owed - val_payable

                defaulter.transfer_cash_to(val_payable, non_defaulter, reason="Partial fulfilment of contract")

                debt_desc = ""
                if debt > 0:
                    bank = get_bank()
                    bank.transfer_cash_to(debt, non_defaulter, reason="Bank payment of debt")

                    debt = Debt(ammount=debt, owed_by=defaulter, owed_to=bank)
                    debt.save()

                    debt_desc = " You now owe a debt of {} to the bank".format(debt.ammount)

                Notification.send_notification(title="Future contract settled", 
                description="The other party defaulted, so you were awarded 1.5x the value of the contract", 
                entity=non_defaulter)


                Notification.send_notification(title="Future contract settled", 
                description="You could not meet your obligation and hence defaulted." + debt_desc, 
                entity=defaulter)

                future.status = Contract.SETTLED
                future.save()
    

class Swap(Asset):
    """ A swap is an agreement for two parties to pay each other
    some ammount at regular intervals based on two different metrics 
    e.g. A pays B 5% of 10million per week
    B pays A 5% of the value of some share each week 
    
    If the value of the share goes up, B loses money
    If the value of the share goes down, B makes money
    
    This is quite complicated, not properly implemented yet """

    party_a = models.ForeignKey(
        Investor,
        related_name="%(app_label)s_%(class)s_partya",
        on_delete=models.CASCADE,
    )
    party_b = models.ForeignKey(
        Investor,
        related_name="%(app_label)s_%(class)s_partyb",
        on_delete=models.CASCADE,
    )

    # These are essentially an equation, could be quite complicated to implement
    a_to_b_payment = models.TextField()
    b_to_a_payment = models.TextField()

    def serialize(self):
        return {"id": self.pk,
        "type": "Swap",}



class BankOffer(models.Model):

    BUY = "B"
    SELL = "S"
    OPTIONS = (
        (BUY, "Buy"),
        (SELL, "Sell")
    )

    TIMEOUT = 10 # seconds

    created = models.DateTimeField(auto_now_add=True)
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    volume = models.DecimalField(max_digits=10, decimal_places=2)
    total_buy_price = models.DecimalField(default=-1, max_digits=10, decimal_places=2)
    total_sell_price = models.DecimalField(default=-1, max_digits=10, decimal_places=2)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)

    def is_valid(self):
        age = current_time() - self.created # type: timedelta
        logger.info("Offer age: {} (seconds)".format(age.total_seconds()))
        return age.total_seconds() < BankOffer.TIMEOUT

    def accept(self, investor: Investor, buy_or_sell: str):
        # perform some checks
        if not self.is_valid():
            raise OfferExpired("This offer has expired")

        seller = None
        buyer = None
        price = 0

        if buy_or_sell == BankOffer.BUY:
            # Investor wants to buy
            buyer = investor
            seller = self.bank
            price = self.total_sell_price # bank sell price
        else:
            # Investor wants to sell
            buyer = self.bank
            seller = investor
            price = self.total_buy_price # bank buy price


        trade = Trade.make_share_trade(self.athlete, self.volume, self.bank, price,
                seller, buyer)

        trade.accept_trade(investor)


    @property
    def expires(self):
        return self.created + timedelta(seconds=self.TIMEOUT)

    def serialize(self):
        return {"id": self.pk,
        "created": self.created,
        "athlete": self.athlete.serialize(),
        "volume": float(self.volume),
        "total_buy_price": float(self.total_buy_price),
        "total_sell_price": float(self.total_sell_price),
        "season": self.season.serialize(),
        "bank": self.bank.serialize(),
        "expires": self.expires,
        }




class Trade(models.Model):
    """ 
    Transfer of a asset between two entities.
    Typically investor to investor
    """

    PENDING = "P"
    ACCEPTED = "A"
    REJECTED = "R"
    CANCELLED = "C"
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (REJECTED, "Rejected"),
        (CANCELLED, "Cancelled"),
    )

    asset = models.ForeignKey(
        Asset, related_name="%(app_label)s_%(class)s_asset", on_delete=models.CASCADE
    )

    seller = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_seller",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    buyer = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_buyer",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    # Who initiated the trade (offered to sell/asked to buy)?
    creator = models.ForeignKey(
        Entity, related_name="%(app_label)s_%(class)s_creator", on_delete=models.CASCADE
    )

    price = models.DecimalField(max_digits=10, decimal_places=2)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # decision_dt = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=PENDING)

    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def __str__(self):
        return "{} from {} to {} for {} ({})".format(
            self.asset, self.seller, self.buyer, self.price, self.status
        )

    def serialize(self):
        json = {
            "id": self.pk,
            "asset": self.asset.serialize(),
            "creator": serialize_entity(
                self.creator
            ),  # self.creator.investor.serialize(),
            "price": self.price,
            "created": self.created,
            "updated": self.updated,
            "status": dict(self.STATUS_CHOICES)[self.status],
        }

        if self.buyer:
            json["buyer"] = serialize_entity(self.buyer)
        if self.seller:
            json["seller"] = serialize_entity(self.seller)

        return json

    @staticmethod
    def check_share_trade_possible(buyer, seller, creator, price, volume, athlete):
        # Check this is possible!
        if buyer and creator == buyer and price > buyer.capital:
            raise InsufficientFunds("Trade price exceeds potential buyer's capital")
            

        if seller and creator == seller:
            s = seller.saleable_shares_in_athlete(athlete)
            if not s or s.volume < volume:
                raise InsufficientShares(
                    f"{seller} does not have this many shares available to sell"
                )


    @staticmethod
    def make_share_trade(
        athlete, volume, creator, price, seller: Investor = None, buyer=None
    ):
        Trade.check_share_trade_possible(buyer, seller, creator, price, volume, athlete)

        virtual_share = Share(
            athlete=athlete, volume=volume, is_virtual=True, season=get_current_season()
        )
        virtual_share.save()

        trade = Trade.make_trade(virtual_share, creator, price, seller, buyer)
        return trade


    @staticmethod
    def make_option_trade(athlete: Athlete, volume: float, creator: Entity, price: float, seller: Entity, 
                        buyer: Entity, strike_date: datetime,  strike_price: float, 
                        option_holder: Entity):
        Trade.check_share_trade_possible(buyer, seller, creator, price, volume, athlete)

        virtual_share = Share(
            athlete=athlete, volume=volume, is_virtual=True, season=get_current_season()
        )
        virtual_share.save()

        option = Option(underlying_asset=virtual_share, strike_time=strike_date, strike_price=strike_price, 
        season=get_current_season(), buyer=buyer, seller=seller, 
         option_holder=option_holder)

        option.save()
        
        trade = Trade.make_trade(asset=option, creator=creator, price=price, seller=seller, buyer=buyer)
        return trade


    @staticmethod
    def make_future_trade(athlete, volume, creator, price, seller, buyer,
                          strike_date, strike_price):
        Trade.check_share_trade_possible(buyer, seller, creator, price, volume, athlete)

        virtual_share = Share(
            athlete=athlete, volume=volume, is_virtual=True, season=get_current_season()
        )
        virtual_share.save()

        future = Future(underlying_asset=virtual_share, strike_time=strike_date, strike_price=strike_price, 
        season=get_current_season(), buyer=buyer, seller=seller)
        future.save()
        
        trade = Trade.make_trade(asset=future, creator=creator, price=price, seller=seller, buyer=buyer)
        return trade

    @staticmethod
    def make_swap_trade(investor, price, seller, buyer, swap_details):
        pass

    @staticmethod
    def sell_existing_contract(contract, seller, buyer, price):
        return Trade.make_trade(contract, seller, price, seller, buyer)

    def make_trade(asset, creator, price, seller=None, buyer=None):
        # price = np.round(price, 2)  # ensure price is always to 2 DP
        trade = Trade(
            asset=asset,
            seller=seller,
            buyer=buyer,
            creator=creator,
            price=price,
            status=Trade.PENDING,
            season=get_current_season(),
        )
        trade.save()
        return trade

    @property
    def status_display(self):
        return dict(self.STATUS_CHOICES)[self.status]

    @property
    def status_detailed(self):
        return self.status_display

    def is_possible(self):
        if self.buyer and self.buyer.capital < self.price:
            return False
    
        if self.seller and self.asset.is_share():
            saleable = self.seller.saleable_shares_in_athlete(self.asset.share.athlete)
            if not saleable or saleable.volume < self.asset.share.volume:
                return False

        # logger.info("Trade is possible: {}".format(self))
        return True

    def reject_trade(self):
        if not self.status == self.PENDING:
            raise TradeNotPending(
                desc="Status of trade is {}".format(self.status_display)
            )

        self.status = self.REJECTED
        self.save()

    def cancel_trade(self):
        if not self.status == self.PENDING:
            raise TradeNotPending(
                desc="Status of trade is {}".format(self.status_display)
            )

        self.status = self.CANCELLED
        self.save()

    def accept_trade(self, action_by, skip_notif=False, notify_both=False):
        if not self.buyer or not self.seller:
            raise NoBuyerOrSeller(
                "To complete this trade there must be a buyer (currently: {}) and a seller (currently: {})".format(
                    self.buyer, self.seller
                )
            )

        if not self.status == self.PENDING:
            raise TradeNotPending("Trade status is {}".format(self.status_display))

        # Check action_by can do this - we must not be the creator
        if action_by == self.creator:
            logger.info("Trade creator = {}".format(self.creator))
            logger.info("Action by = {}".format(action_by))
            raise NoActionPermission("You cannot accept a trade which you initiated")

        # Check buyer has cash
        trade_price = self.price
        if not self.buyer.capital >= self.price:
            raise InsufficientFunds(
                "Buyer ({}) does not have enough funds ({} < {})".format(
                    self.buyer.print_name, self.buyer.capital, self.price
                )
            )     

        other_party = self.seller
        if self.seller == action_by:
            other_party = self.buyer

        # Now do asset specfic checks and action the trade
        transaction_reason = "Unknown"
        if self.asset.is_share():

            if not self.seller.can_sell_asset(self.asset):
                raise InsufficientShares(
                    "Seller ({}) does not have sufficient shares to fulfill trade.".format(self.seller.print_name)
                )

            # Do the trade
            logger.info(
                "Accepted trade: {}".format(self)
            )  
            share = self.seller.get_share(self.asset.share)
            share.transfer(to=self.buyer, vol=self.asset.share.volume)

            # Send notification to not actioner
            common = "Share: {} ({:.2f}) for {:.2f}".format(self.asset.share.athlete.name, self.asset.share.volume, self.price)
            Notification.send_notification(title="Trade accepted", description="{} accepted the trade for {}".format(action_by, common), entity=other_party)
            if notify_both:
                Notification.send_notification(title="Trade accepted", description="{} accepted the trade for {}".format(other_party, common), entity=action_by)

            transaction_reason = "Share trade: " + str(self)

        elif self.asset.is_future() or self.asset.is_option():
            # Only one check to perform - can purchaser of contract pay the trade price?
            # This is already done.
            
            contract = self.asset.contract
            future = self.asset.contract.future

            # 1) Confirm contract
            # Either there is currently an open spot, in which case the buyer takes that spot
            # Or one of the two involved parties is selling
            # their position (as either the future buyer or seller) to someone else.
            # The trade buyer replaces the trade sellers position

            if future.seller and future.buyer:
                if self.seller == future.seller:
                    future.seller = self.buyer
                elif self.seller == future.buyer:
                    future.buyer = self.buyer   
                else:
                    # This should never happen!
                    raise XChangeException(f"Contract seller ({self.seller}) was not involved in the contract (between {future.seller} and {future.buyer})!")
            elif future.seller is None:
                    future.seller = action_by
            elif future.buyer is None:
                    future.buyer = action_by
            else:
                raise XChangeException("This should never happen")


            if self.asset.is_option():
                # sort out the option holder
                # if option holder is involved in option, all is good
                opt = future.option
                if opt.option_holder in (future.buyer, future.seller):
                    pass
                else:
                    # otherwise, we need to find the holder
                    # it must be the new party into the contract?
                    opt.option_holder = action_by
            
            if future.seller is None or future.buyer is None:
                raise XChangeException(f"Future/option does not have buyer ({future.buyer}) and/or seller ({future.seller}). Action by: {action_by}")

            if future.seller == future.buyer:
                raise XChangeException(f"The future/option buyer ({future.buyer}) cannot be the same as the future seller ({future.seller})")

            if self.asset.is_option():
                opt.save()
                
            contract.status = Contract.ACTIVE
            future.save()
            self.asset.contract.save()
            self.asset.save()

            # 2) Schedule settlement action
            # settle_future(future, schedule=future.strike_time)
            # For testing, just schedule 5 seconds in the future
            if settings.TESTING_FUTURES_TIMING > 0:
                schedule = settings.TESTING_FUTURES_TIMING
                #  self.asset.contract.future.strike_time = datetime.now() +  timedelta(seconds=settings.TESTING_FUTURES_TIMING)
                #  self.asset.contract.future.save()
            else:
                schedule = self.asset.contract.future.strike_time
            settle_future(self.asset.contract.future.pk, schedule=schedule)


            fut = self.asset.contract.future
            sell_string = ""
            if fut.seller:
                sell_string = f"{fut.seller} to sell"
            else:
                sell_string = f"{fut.buyer} to buy"
            common = "Future: ({} {} shares in {} for {}). Trade price: {}".format(sell_string, fut.underlying_asset.volume, fut.underlying_asset.athlete.name, fut.strike_price, self.price)
            Notification.send_notification(title="Trade accepted", description="{} accepted the trade for contract: {}".format(action_by, common), entity=other_party)
            
            transaction_reason = "Entered contract: " + common
        else:
            logger.info("Unable to complete trade for {}".format(self.asset))
            return

        b = self.buyer
        b.transfer_cash_to(ammount=self.price, to=self.seller, reason=transaction_reason)

        self.seller.save()
        self.buyer.save()

        self.status = self.ACCEPTED
        self.save()


    def partially_fill_with(self, other_trade: 'Trade') -> None:
        """ 
        Partially fill this trade by matching with another.
        """

        if not self.status == Trade.PENDING and other_trade.status == Trade.PENDING:
            raise XChangeException("Both trades not pending")

        # Some basic tests - should possibly raise exceptions here
        if not self.asset.share.athlete == other_trade.asset.share.athlete:
            # Trades not same athlete
            raise XChangeException("Attempting to fill trade with different athletes")

        if (self.buyer and other_trade.seller) and (self.seller and other_trade.buyer):
            # Trades not compatible
            raise XChangeException("Attempting to fill trades which aren't open to buy/sell")
        
        # Can't trade with ourself!
        if self.creator == other_trade.creator:
            raise XChangeException("Attempting to fill trade with one created by the same investor")
        
        if self.seller and self.seller == other_trade.buyer:
            raise XChangeException("Attempting to fill trade by buying from the same investor")
        
        if self.buyer and self.buyer == other_trade.seller:
            raise XChangeException("Attempting to fill trade by selling to the same investor")

        # This trade must have greater volume
        if not self.asset.share.volume >= other_trade.asset.share.volume:
            raise XChangeException("Attempting to fill trade with another trade of greater volume")

        # Now do the work
        volume_to_trade = other_trade.asset.share.volume
        unfilled_volume = self.asset.share.volume - volume_to_trade

        matched_price_per_vol = (self.price/self.asset.share.volume 
                                + other_trade.price/other_trade.asset.share.volume)/2
        matched_price = matched_price_per_vol * volume_to_trade

        # Update smaller trade for the actual trade we're going to make
        other_trade.price = matched_price

        if self.seller and not self.buyer:
            other_trade.seller = self.seller
        elif self.buyer and not self.seller:
            other_trade.buyer = self.buyer
        else:
            # This also shouldn't happen
            return

        # New trade:
        original_volume = self.asset.share.volume
        try:

            # Accept the smaller trade at the matched price
            other_trade.accept_trade(action_by=self.creator, notify_both=True)
            
            # Update this trade for the new volume
            self.price = self.price * (unfilled_volume/self.asset.share.volume)
            self.asset.share.volume = unfilled_volume
            self.asset.share.save()
            self.save()
            logger.info("**Successfully filled trade, remaining volume = {:.2f}".format(unfilled_volume))
        except XChangeException as e:
            logger.info(e)
        
        
    
@background(schedule=0)
def match_partial_trades():
    """ Match partial trades. 
    Prioritise by the best deal, 
    then the earlier trade in case of a tie break"""
    # Get all open and pending trades
    active_trades = Trade.objects.all().filter(status=Trade.PENDING).order_by('created')

    open_trades = [trade_to_fill for trade_to_fill in active_trades if 
                (trade_to_fill.seller is None or trade_to_fill.buyer is None) 
                and trade_to_fill.asset.is_share()]

    trades_with_no_seller = [trade_to_fill for trade_to_fill in open_trades if trade_to_fill.seller==None]
    trades_with_no_buyer = [trade_to_fill for trade_to_fill in open_trades if trade_to_fill.buyer==None]

    # loop through from earliest to latest, trying to fulfil each order
    for trade_to_fill in open_trades:
        logger.info("Fill trade: {}".format(trade_to_fill))

        trade_to_fill.refresh_from_db() # just in case this trade has already been modified earlier in the loop

        if trade_to_fill.asset.share.volume <= 0 or not trade_to_fill.status == Trade.PENDING:
            continue

        matching_trades = Trade.objects.all().filter(Q(asset__share__athlete=trade_to_fill.asset.share.athlete)
                                                        & ~Q(creator=trade_to_fill.creator) & 
                                                        Q(status=Trade.PENDING)
                                                        & Q(asset__share__volume__gt=0)).order_by('-price')

        this_price_per_vol = trade_to_fill.price / trade_to_fill.asset.share.volume
        if not trade_to_fill.seller:
            # try to find a seller who wants to sell for <= buy price
            # try to find the smallest price
            matching_trades = matching_trades.filter(Q(buyer=None)
            & ~Q(seller=trade_to_fill.buyer)
            )
            matching_trades = [t for t in matching_trades if t.price/t.asset.share.volume < this_price_per_vol]
            # matching_trades = [t for t in matching_trades if not t.seller == trade_to_fill.buyer]
        elif not trade_to_fill.buyer:
            matching_trades = matching_trades.filter(Q(seller=None)
                & ~Q(buyer=trade_to_fill.seller)
                )
            matching_trades = [t for t in matching_trades if t.price/t.asset.share.volume > this_price_per_vol]
            # matching_trades = [t for t in matching_trades if not t.buyer == trade_to_fill.seller]
        else:
            # This should never happen, but just in case
            continue
        
        logger.info("  Matching trades ({}):".format(len(matching_trades)))
        for t in matching_trades:
            logger.info(f"   {t}")

            # how we match the trades depends on which has the largest volume

            if trade_to_fill.asset.share.volume >= t.asset.share.volume:
                trade_to_fill.partially_fill_with(t)
            else:
                t.partially_fill_with(trade_to_fill)

            # If we've managed to completely fill this trade, move on
            if trade_to_fill.asset.share.volume == 0:
                break



@receiver(pre_save, sender=Trade)
def update_on_trade_acceptance(sender, instance, **kwargs):
    """ Update indexes rating """
    
    if instance.id:
        old_trade = Trade.objects.get(pk=instance.id)
        if old_trade.status == Trade.PENDING and instance.status == Trade.ACCEPTED:
            # Recompute top 10 index
            schedule_share_calculation()

            if instance.asset.is_contract():

                party_a = None
                party_b = None

                if instance.asset.is_future() or instance.asset.is_option():
                    party_a = instance.asset.contract.future.buyer
                    party_b = instance.asset.contract.future.buyer
                    
                elif instance.asset.is_swap():
                    pass

                if party_a is None or party_b is None:
                    raise XChangeException(f"Party A ({party_a}) and party b ({party_b}) must exist")

                c = ContractHistory(party_a=party_a, party_b=party_b, contract=instance.asset.contract)
                c.save()
            
@receiver(post_save, sender=Trade)
def compute_shares_owned(sender, instance, **kwargs):
    if instance.status == Trade.ACCEPTED:
        ShareOwnership.create_for_entity(entity=instance.buyer)
        ShareOwnership.create_for_entity(entity=instance.seller)


@background(schedule=5)
def schedule_share_calculation():
    """ Compute shares indexes in 5 seconds time """
    ShareIndexValue.compute_value(ShareIndexValue.TOP10)

class LoanOffer(models.Model):
    """ Determine what loans are on offer from a bank
    Can be overriden by new models which provide more complex options if required """
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    interest_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Fractional interest rate")
    repayment_interval = models.DurationField(default=timedelta(days=7))

    def __str__(self):
        return "{}/{}/{}".format(self.bank, self.interest_rate, self.repayment_interval)

    def compute_interest_rate(self, recipient=None) -> float:
        """ This can be overriden by child classes to provide more complicated
        interest rates e.g. based on the investors likelihood of repaying the load
        """
        return float(self.interest_rate)

    

class Loan(models.Model):
    """ One entity may loan another entity some capital, which is repayed at some interest rate
    """

    lender = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_lender",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
    )
    recipient = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_recipient",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
    )

    created = models.DateTimeField(auto_now_add=True)

    last_processed = models.DateTimeField(auto_now_add=True)
    next_payment_due = models.DateTimeField()

    # Interest rate as a fraction e.g. 0.01 = 1% on the repayment interval
    interest_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Fractional interest rate")

    # How much needs to be repayed
    balance = models.DecimalField(max_digits=10, decimal_places=2)

    # Default interval is weekly
    repayment_interval = models.DurationField(default=timedelta(days=7))

    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def serialize(self):
        return {
            "id": self.id,
            "lender": serialize_entity(self.lender),
            "recipient": serialize_entity(self.recipient),
            "created": self.created,
            "last_processed": self.last_processed,
            "next_payment_due": self.next_payment_due,
            "interest_rate": self.interest_rate,
            "balance": self.balance,
            "repayment_interval": self.repayment_interval,
        }

    def __str__(self):
        return "Loan of {} from {} to {} ({}% interest)".format(
            self.balance, self.lender, self.recipient, self.interest_rate
        )

    def create_loan(lender, recipient, interest, balance, interval :timedelta):

        # Perform checks
        # Can't lend money you don't have
        if lender.capital < balance:
            raise InsufficientFunds(
                "Lender has {} which is less than the balance {}".format(
                    lender.capital, balance
                )
            )

        next_payment_due = current_time() + interval
        loan = Loan(
            lender=lender,
            recipient=recipient,
            interest_rate=interest,
            balance=balance,
            repayment_interval=interval,
            next_payment_due=next_payment_due,
            season=get_current_season()
        )
        logging.info("Recipient capital before loan received: {}".format(recipient.capital))
        lender.transfer_cash_to(balance, recipient, reason="Loan created: " + str(loan))
        logging.info("Recipient capital after loan received: {}".format(recipient.capital))

        lender.save()
        recipient.save()
        loan.save()

        logger.info("Interval: " + str(interval))
        logger.info("Scheduling loan with repeat: {} seconds".format(interval.total_seconds()))
        Loan.schedule_accrue_interest(loan.id, repeat=interval.total_seconds(), repeat_until=None)    

    
    @background(schedule=0)
    def schedule_accrue_interest(loan_id):
        loan = Loan.objects.get(id=loan_id)
        loan.accrue_interest()


    def accrue_interest(self):

        # Check if it is indeed time to repay - is this approximately the time that the next repayment is due?
        # diff = current_time() - self.next_payment_due
        # if not np.abs(diff.seconds) < np.abs(self.repayment_interval.seconds) / 10.0:
        #     return

        if self.balance == 0:
            # Delete this task
            # task = BackgroundTask.objects.all().filter(task_params="[[{}], \{\}]".format(self.id), task_name="app.models.loan.pay_interest")
            # task.delete()
            raise Exception("Loan balance = 0, manually delete task")
            

        # interest_ammount = np.round(self.interest_rate * self.balance, 2)
        interest_ammount = self.interest_rate * self.balance
        logger.info(
            "Accrue interest {} from {} to {}".format(
                interest_ammount, self.recipient, self.lender
            )
        )

        self.balance = self.balance + interest_ammount
        self.save()

    
    def repay_loan(self, ammount):
        try:
            if ammount > self.balance:
                ammount = self.balance
            if ammount <= 0:
                return
            self.recipient.transfer_cash_to(ammount, self.lender, reason="Loan repayment: "+ str(self))
        except XChangeException as e:
            raise e

        self.balance = self.balance - ammount
        self.save()


# def pay_all_loans():
#     loans = (
#         Loan.objects.all()
#         .filter(next_payment_due__lte=current_time(),season=get_current_season())
#         .exclude(balance=0)
#     )

#     for l in loans:
#         l.pay_interest()


class Debt(models.Model):
    """ Having introduced loans, we must now allow for debt 
    E.g. if someone is unable to pay back a loan
    """

    owed_by = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_owed_by",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
    )
    owed_to = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_owed_to",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
    )

    created = models.DateTimeField(auto_now_add=True)

    ammount = models.DecimalField(max_digits=10, decimal_places=2)

    def serialize(self):
        return {
            "owed_by": self.owed_by.serialize(),
            "owed_to": self.owed_to.serialize(),
            "created": self.created,
            "ammount": self.ammount,
        }


@receiver(pre_save, sender=Debt)
def update_debt(sender, instance: Debt, **kwargs):
    """ Update capital of debt owed to/by rating """
    
    if instance.id:
        old_debt = Debt.objects.get(pk=instance.id)
        
        # update capital of owed by / to
        repayment_ammount = old_debt.ammount - instance.ammount

        # Can only ever decrease debt
        if repayment_ammount < 0:
            raise APIException("Cannot repay a negative ammount of debt")

        if instance.ammount < 0:
            raise APIException("Cannot repay more than the debt")

        # This should through exceptions if this repayment is invalid
        instance.owed_by.transfer_cash_to(repayment_ammount, instance.owed_to, reason="Debt repayment")




class TransactionHistory(models.Model):
    """ We should keep a track of all transactions made """

    SHARE_REASON = r"([a-zA-Z\s]+): ([\d\.]+).*from ([a-zA-Z\s]+).* to ([a-zA-Z\s]+).*for ([\d\.]+).*"

    sender = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_from",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
    )
    recipient = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_to",
        on_delete=models.CASCADE,
        blank=False,
        null=False,
    )
    ammount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = (
        models.TextField()
    )  # e.g. buying volume of shares from X, repaying loan to X
    timestamp = models.DateTimeField(auto_now_add=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    # Keep track of the sender and recipient capital after the trade
    sender_capital = models.DecimalField(max_digits=10, decimal_places=2)
    recipient_capital = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return "{} from {} to {} at {}".format(self.ammount, self.sender, self.recipient, self.timestamp)

    def serialize(self):
        return {
            "sender": self.sender.serialize(),
            "recipient": self.recipient.serialize(),
            "ammount": self.ammount,
            "reason": self.reason,
        }

    
    def description(self, investor: Investor):

        
        share_match = re.match(TransactionHistory.SHARE_REASON, self.reason.replace('Share trade: ', ''))
        if share_match:
            athlete = share_match.groups()[0]
            volume = float(share_match.groups()[1])
            sender = share_match.groups()[2]
            recipient = share_match.groups()[3]
            price = float(share_match.groups()[4])

            athlete = Athlete.objects.get(name=athlete)

            # trade = Trade.objects.get(status=Trade.ACCEPTED,seller__name=sender,buyer__name=recipient,asset__share__athlete__name=athlete)

            desc = ""
            other_party = ""
            from_to = ""
            if self.recipient == investor:
                desc = desc + "Sold "
                other_party = self.sender
                from_to = "to"
            else:
                desc = desc + "Bought "
                other_party = self.recipient
                from_to = "from"

            desc = desc + " {0:.2f} shares in {1} {2} {3}".format(volume, athlete.to_html, from_to, other_party.to_html)
            return desc

        else:
            logger.info("Couldn't determine transaction reason")

        return self.reason

    def capital_for(self, entity: Entity):
        if self.recipient == entity:
            return self.recipient_capital
        elif self.sender == entity:
            return self.sender_capital
        else:
            raise XChangeException("Entity not involved in transaction")
        
    def cash_in(self, investor: Investor):
        if self.sender == investor:
            return ""
        else:
            return self.ammount
        
    
    def cash_out(self, investor: Investor):
        if self.recipient == investor:
            return ""
        else:
            return self.ammount
        

    @property
    def transaction_type(self):

        share_match = re.match(TransactionHistory.SHARE_REASON, self.reason)
        if share_match:
            return "Trade (Share)"

        return None
        # return "type"

    
    def balance(self, investor: Investor):
        return investor.get_capital(self.timestamp + timedelta(milliseconds=1))

@receiver(pre_save, sender=TransactionHistory)
def set_capital(sender, instance : TransactionHistory, **kwargs):

    instance.recipient.refresh_from_db()
    instance.sender.refresh_from_db()

    instance.recipient_capital = instance.recipient.capital
    instance.sender_capital = instance.sender.capital



class Event(models.Model):
    """ Athletes compete in Events and hence earn dividends """

    name = models.CharField(max_length=100)
    date = models.DateField()
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def __str__(self):
        return "{} ({})".format(self.name, self.date.strftime("%d/%m/%Y"))

    def serialize(self):
        return {"name": self.name, "date": self.date}


class Race(models.Model):
    """ Many races per event """

    event = models.ForeignKey(
        Event, related_name="%(app_label)s_%(class)s_event", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100)
    time = models.DateTimeField()
    results_link = models.URLField(blank=True, null=True)
    event_details_link = models.URLField(blank=True, null=True)
    max_dividend = models.DecimalField(max_digits=10, decimal_places=2)
    min_dividend = models.DecimalField(max_digits=10, decimal_places=2, default=10.0)
    num_competitors = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return "{} - {} ({})".format(self.event.name, self.name, self.time.strftime("%d/%m/%Y %H:%m"))

    def serialize(self):
        return {
            "event": self.event.serialize(),
            "name": self.name,
            "time": self.time,
            "results_link": self.results_link,
            "event_details_link": self.event_details_link,
            "max_dividend": float(self.max_dividend),
            "min_dividend": float(self.min_dividend),
            "num_competitors": self.num_competitors,
        }

    def compute_dividends(self):
        results = Result.objects.all().filter(race=self)

        # Perform some checks
        if len(results) == 0:
            return "No results uploaded yet for this race"

        if not self.num_competitors or self.num_competitors == 0:
            return "Number of competitors for this race hasn't been entered."

        # Now actually compute dividends
        compute_dividends(self)

        return None

    def distribute_dividends(self):
        results = Result.objects.all().filter(race=self)
        if len(results) == 0:
            return "No results uploaded yet for this race"

        # Check dividends have been computed
        for r in results:
            if not r.dividend:
                return "Dividends have not been computed for a competitor in this race: {}".format(
                    r.athlete.name
                )

        # Now distribute
        for r in results:
            for i in Investor.objects.all():
                shares_owned = i.shares_in_athlete(r.athlete)
                if not shares_owned or shares_owned.volume == 0:
                    continue

                vol_owned = shares_owned.volume

                dividend_earned = vol_owned * r.dividend

                try:
                    bank = cowley_club_bank()
                    bank.transfer_cash_to(
                        dividend_earned, i, reason="Dividend payment {}".format(r.id)
                    )

                    r.dividend_distributed = True
                    r.save()

                except XChangeException as e:
                    return "{}: {}".format(e.title, e.desc)

        return None


class Result(models.Model):
    """ Results are recorded for athletes when they
    perform well in an event.

    They are entered manually by the XChange administrator, and automatically distributed 
    in a proportional manner to those
    who owned shares in the athlete at the start of the event. 
    """

    athlete = models.ForeignKey(
        Athlete,
        related_name="%(app_label)s_%(class)s_athlete",
        on_delete=models.CASCADE,
    )
    race = models.ForeignKey(Race, on_delete=models.CASCADE)
    position = models.IntegerField()
    time = models.DurationField(null=True, blank=True)
    dividend = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    dividend_distributed = models.BooleanField(default=False)

    class Meta:
       unique_together = ('race', 'athlete',)

    def serialize(self):
        return {
            "athlete": self.athlete.serialize(),
            "race": self.race.serialize(),
            "position": self.position,
            "time": self.time,
            "dividend": self.dividend,
            "dividend_distributed": self.dividend_distributed,
        }

    def __str__(self):
        return "{}. {} ({} - {})".format(self.position, self.athlete.name, self.race.name, self.race.event.name)


# For dealing with auctions
class Auction(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE)
    is_current = models.BooleanField(default=False)

    def __str__(self):
        return "{} (Ends: {})".format(self.name, self.end_date)

    # TODO: on create hook - populate lots with bank owned shares

class Lot(models.Model):
    athlete = models.ForeignKey(
        Athlete,
        related_name="%(app_label)s_%(class)s_athlete",
        on_delete=models.CASCADE,
    )
    volume = models.DecimalField(max_digits=10, decimal_places=2)
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE)

    def __str__(self):
        return "{} ({:.2f})".format(self.athlete.name, self.volume)

@receiver(post_save, sender=Auction)
def create_lots_after_auction_created(sender, instance : Auction, created, **kwargs):
    if created:
        bank_shares = instance.bank.get_shares_owned()

        for share in bank_shares:
            lot = Lot(athlete=share.athlete, volume=share.volume, auction=instance)
            lot.save()

class Bid(models.Model):
    PENDING = "P"
    ACCEPTED = "A"
    REJECTED = "R"
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (REJECTED, "Rejected"),
    )

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=PENDING)

    bidder = models.ForeignKey(
        Entity, related_name="%(app_label)s_%(class)s_bidder", on_delete=models.CASCADE
    )
    # auction = models.ForeignKey(Auction, on_delete=models.CASCADE)
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    volume = models.DecimalField(max_digits=10, decimal_places=2)
    price_per_volume = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        # Each bidder can only have one bid on a lot
        unique_together = ('bidder', 'lot',)


class ShareOwnership(models.Model):
    """
    Store record of shares owned by entity at a specific time
    stored as a dict:
    { 
        "athlete_id": vol_owned
    }
    """

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    share_vol_owned = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.entity.print_name}, {self.timestamp}"

    @staticmethod
    def create_for_entity(entity: Entity, time: datetime=None) -> 'ShareOwnership':

        vol = {}

        shares_owned = entity.get_shares_owned()

        for share in shares_owned:
            vol[share.athlete.id] = float(share.volume)

        obj = ShareOwnership(entity=entity, share_vol_owned=json.dumps(vol))
        if time:
            obj.timestamp = time

        obj.save()
        return obj


            

class Notification(models.Model):
    UNSEEN = 'U'
    SEEN = 'S'
    DISMISSED = 'D'
    STATUSES = (
        (UNSEEN, "Unseen"),
        (SEEN, "Seen"),
        (DISMISSED, "Dismissed"),
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    datetime = models.DateTimeField(auto_now_add=True)
    # seen = models.BooleanField(default=False)
    status = models.CharField(choices=STATUSES,max_length=1, default=UNSEEN)
    investor = models.ForeignKey(Investor, on_delete=models.CASCADE)

    def __str__(self):
        return "Notification to {}: {} ({})".format(self.investor.name, self.title, self.datetime)

    @staticmethod
    def send_notification(title, description, entity: Entity):
        if not entity.is_investor():
            return
        
        n = Notification(title=title, description=description, investor=entity.investor)
        n.save()        

    def serialize(self):
        return {"id": self.id,
        "title": self.title,
        "description": self.description,
        "datetime": self.datetime,
        "status": self.get_status,
        "investor": serialize_entity(self.investor) }

    @property
    def get_status(self):
        return dict(self.STATUSES)[self.status]
    # @staticmethod
    # def get_unseen_for_investor(investor: Investor):
    #     notifs = Notification.objects.all().filter(Q(investor=investor) & ~Q(status=Notification)).order_by('-datetime')
    #     return notifs


class TradePartialFill:
    """ Represents a fraction of a current trade """
    trade: Trade
    filled_volume: decimal.Decimal

    def __init__(self, trade, volume):
        self.trade = trade
        self.filled_volume = volume

    def get_price_per_vol(self):
        return self.trade.price/self.trade.asset.share.volume 

    def get_price(self):
        return self.get_price_per_vol() * self.filled_volume

    def accept(self, investor, buy_or_sell):
        """ Accept this partial trade """
        if self.trade.asset.share.volume == self.filled_volume:
            logger.info("Fill full trade: %s", self.trade)

            if buy_or_sell == Offer.BUY:
                if self.trade.buyer is not None and self.trade.buyer is not investor:
                    raise XChangeException("Trade already has different buyer")

                self.trade.buyer = investor
            else:
                if self.trade.seller is not None and self.trade.seller is not investor:
                    raise XChangeException("Trade already has different seller")
                self.trade.seller = investor

            self.trade.accept_trade(investor)
        else:
            # Partially fill the trade, which is more complicated
            # First create new trade for the volume we actually want
            if self.trade.buyer is None:
                buyer = investor
                seller = self.trade.seller

            else:
                buyer = self.trade.buyer
                seller = investor

            new_trade = Trade.make_share_trade(self.trade.asset.share.athlete, self.filled_volume,
            investor, self.get_price(), seller, buyer)
            new_trade.save()

            # Now fill existing trade with the new trade
            self.trade.partially_fill_with(new_trade)

        self.trade.save()


class Offer:
    """
    When an investor wants to buy/sell shares in an athlete,
    this may be possible by combining various open trades
    along with buying/selling some portion with the bank

    This class represents the collection of these trades.
    """
    BUY = "B"
    SELL = "S"
    OPTIONS = (
        (BUY, "Buy"),
        (SELL, "Sell")
    )

    investor: Investor
    trades: List[TradePartialFill]
    bank_offer: BankOffer
    athlete: Athlete
    volume: decimal.Decimal
    is_available: bool


    def __init__(self, investor: Investor, athlete: Athlete, volume: decimal.Decimal, buy_or_sell: str):
        self.investor = investor
        self.athlete = athlete
        self.volume = decimal.Decimal(volume)
        self.is_available = False
        self.buy_or_sell = Offer.BUY if buy_or_sell in ("B", "Buy", "buy") else Offer.SELL
        self.trades = []

    def compute_offer(self):
        """
        Compute offer by considering available trades
        and bank offers 
        """
        # Reset flag
        self.is_available = False
        self.bank_offer = None
        self.trades = []

        # Consider bank
        bank = get_bank()
        bank_offer = bank.get_buy_sell_offer(self.athlete.id, self.volume)
        bank_offer_total = bank_offer.total_sell_price  if self.buy_or_sell == self.BUY else bank_offer.total_buy_price
        bank_offer_per_unit = bank_offer_total / self.volume
        logger.info("Bank offer: bank will %s volume %s for %s per unit", self.buy_or_sell,self.volume,  bank_offer_per_unit)


        # TODO: Consider trades with other players
        # Get all open trades for this athlete
        valid_trades = []
        if self.buy_or_sell == self.BUY:
            # We want to buy - find all trades without a buyer
            matching_trades = Trade.objects.all().filter(Q(asset__share__athlete=self.athlete)
                                                        & ~Q(creator=self.investor)
                                                        & Q(status=Trade.PENDING)
                                                        & Q(buyer=None)
                                                        & Q(asset__share__volume__gt=0)
                                                        & Q(season=get_current_season()) ).order_by('-price')
        
            
        else:
            # We want to sell - find all trades without a seller
            matching_trades = Trade.objects.all().filter(Q(asset__share__athlete=self.athlete)
                                                        & ~Q(creator=self.investor)
                                                        & Q(status=Trade.PENDING)
                                                        & Q(seller=None)
                                                        & Q(asset__share__volume__gt=0)
                                                        & Q(season=get_current_season()) ).order_by('-price')
       
        for trade in matching_trades:
            trade.price_per_unit = trade.price/trade.asset.share.volume

        
        matching_trades = sorted(matching_trades, key = lambda t: t.price_per_unit)

        if self.buy_or_sell == self.SELL:
            matching_trades.reverse()

        logger.info("Possible trades: ")
        for trade in matching_trades:
            logger.info("%d: %s %s (%s) for %s (%s per unit) with %s", trade.id, self.buy_or_sell,
            trade.asset.share.athlete.name, trade.price, trade.asset.share.volume,
            trade.price_per_unit,
            trade.creator)

        # Start accumulating trades whilst the price is better than the bank price
        volume_to_fill = self.volume
        for trade in matching_trades:

            logger.info("Looking to %s, considering trade with price/unit: %s vs bank %s", self.buy_or_sell, trade.price_per_unit, bank_offer_per_unit)

            if (self.buy_or_sell == self.BUY and trade.price_per_unit < bank_offer_per_unit) or (self.buy_or_sell == self.SELL and trade.price_per_unit > bank_offer_per_unit):

                trade_volume = min(trade.asset.share.volume, volume_to_fill)

                # Check trade is actually possible
                if self.buy_or_sell == self.BUY:
                    buyer = self.investor
                    seller = trade.seller
                else:
                    buyer = trade.buyer
                    seller = self.investor

                try:
                    Trade.check_share_trade_possible(buyer, seller, trade.creator,
                                                trade.price_per_unit*trade_volume,
                                                trade_volume, self.athlete)

                except XChangeException as e:
                    # trade is not possible, try next one
                    logger.info("Trade not possible because: %s", e)
                    continue

                logger.info("Fill volume %s from trade %s", trade_volume, trade.id)
                self.trades.append(TradePartialFill(trade, trade_volume))

                volume_to_fill = volume_to_fill - trade_volume

                if volume_to_fill == 0:
                    break
            else:
                logger.info("Don't do trade %s", trade.id)
                break

        # If remaining volume to fill, fill with bank
        if volume_to_fill > 0:
            bank_offer = bank.get_buy_sell_offer(self.athlete.id, volume_to_fill)
            bank_offer_total = bank_offer.total_sell_price  if self.buy_or_sell == self.BUY else bank_offer.total_buy_price

            if bank_offer_total > 0:
                self.bank_offer = bank_offer

                logger.info("Fill remaining volume (%s) with bank offer: %s", volume_to_fill, bank_offer_total)
                volume_to_fill = 0

            else:
                self.bank_offer = None
                logger.info("Unable to fill remaining volume with bank offer")

        # If we've filled the requirements, set offer as available
        if volume_to_fill == 0:
            logger.info("Offer is available")
            self.is_available = True
        else:
            self.is_available = False
            logger.info("No offer available")


    def accept(self, total_price: decimal.Decimal):

        # Get latest offer, check still valid
        self.compute_offer()

        logger.info("Latest offer: %s, desired price: %s", self.get_total_price_of_offer(), total_price)

        if abs(self.get_total_price_of_offer() - total_price) > 0.01:
            logger.info("Offer no longer available %s != %s", total_price, self.get_total_price_of_offer())
            raise OfferExpired(f"Price {total_price} no longer available, please refresh")

        volume_to_fill_with_trades = self.volume

        if self.bank_offer:
            self.bank_offer.accept(self.investor, self.buy_or_sell)
            volume_to_fill_with_trades = volume_to_fill_with_trades - decimal.Decimal(self.bank_offer.volume)

        if self.trades:
            for partial_trade in self.trades:
                partial_trade.accept(self.investor, self.buy_or_sell)


    def get_total_price_of_offer(self):
        """
        Sum up price of trades and bank offer that constitute this offer
        Computes offer if not done already
        Returns NaN if no offer available
        """
        if not self.is_available:
            self.compute_offer()

        if not self.is_available:
            logger.info("No offer available")
            return -1

        total_price = 0
        if self.trades:
            for trade in self.trades:
                total_price = total_price + trade.get_price()

        if self.bank_offer:
            if self.buy_or_sell == self.BUY:
                # We want to buy, get bank sell price
                total_price = total_price + self.bank_offer.total_sell_price
            else:
                # We want to sell, get bank buy price
                total_price = total_price + self.bank_offer.total_buy_price

        return total_price



def compute_dividends(race: Race):
    if not race.num_competitors:
        return

    results = Result.objects.all().filter(race=race)
    for r in results:
        scaled_position = (
            race.num_competitors - (r.position - 1)
        ) / race.num_competitors
        r.dividend =  race.min_dividend + (race.max_dividend - race.min_dividend) * pow(scaled_position, 2),
            
        r.save()


def cowley_club_bank():
    bank = Bank.objects.get(name="The Cowley Club Bank")
    return bank

