from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from datetime import timedelta, datetime
import pytz
import numpy as np
from app.errors import *
from django.db.models import Q
from django.contrib import admin  # .admin.ModelAdmin import message_user
import re
from background_task import background
from django.db.models.signals import pre_save
import logging

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
    capital = models.FloatField(default=INITIAL_CAPITAL)

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
                current_capital = current_capital - t.ammount

            else:
                current_capital = current_capital + t.ammount

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

        for t in cash_transactions:

            # If this investor sent the money, then return state to before this (add money)
            if t.sender == self:
                investor_capital = investor_capital - t.ammount
            else:
                investor_capital = investor_capital + t.ammount

            cash_positions.append(
                {
                    "time": round_time(t.timestamp),
                    "value": investor_capital,
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

        asset_transactions = (
            Trade.objects.all().filter(status=Trade.ACCEPTED).order_by("updated")
        )
        share_transactions = [t for t in asset_transactions if t.asset.is_share()]

        investor_shares = {}

        # Assume everyone starts with 0 shares
        share_positions = [
            {
                "time": round_time(get_current_season().start_time),
                "value": 0.0,
                "type": "share",
            }
        ]

        # Now for each share transaction, re compute
        for t in share_transactions:
            share = t.asset.share
            athlete = share.athlete

            # Track shares owner by investor
            if not athlete.name in list(investor_shares.keys()):
                investor_shares[athlete.name] = {"vol": 0}

            if share.volume == 0:
                logger.info("Share has zero volume: {}".format(share))
            else:
                investor_shares[athlete.name]["val"] = t.price / share.volume

            if t.buyer == self:
                investor_shares[athlete.name]["vol"] = (
                    investor_shares[athlete.name]["vol"] + share.volume
                )

            # If the investor sold the share at this point, re add it to the
            elif t.seller == self:
                investor_shares[athlete.name]["vol"] = (
                    investor_shares[athlete.name]["vol"] - share.volume
                )

            total_share_val = 0
            for athlete, share in investor_shares.items():
                total_share_val = total_share_val + share["vol"] * share["val"]

            share_positions.append(
                {
                    "time": round_time(t.updated),
                    "value": total_share_val,
                    "type": "share",
                }
            )

        share_positions.append(
            {"time": round_time(this_time), "value": total_share_val, "type": "share"}
        )

        
        
        # Now do derivatives. Recalculate this after every trade
        # As share trades affect derivative pricing
        # again, assume everyone starts with 0 derivatives
        derivative_transactions = [t for t in asset_transactions] #  if t.asset.is_derivative()
        derivatives = [{"time": round_time(get_current_season().start_time), "value": 0.0, "type": "derivative"}]
    
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
                    {"time": t["time"], "value": running_cash + running_shares + running_derivs}
                )

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

        contracts = Contract.objects.all()
        owned_contracts = []
        for c in contracts:
            relevant_history = ContractHistory.objects.all().filter(Q(contract=c) & Q(timestamp__lte=timestamp))
            relevant_history = relevant_history.order_by('-timestamp')

            if len(relevant_history) > 0:
                most_recent = relevant_history[0]
                if most_recent.owner == self or most_recent.other_party == self:
                    owned_contracts.append(c)

        return owned_contracts

    def get_shares_wealth(self):
        """ Get entities current share holding value """
        shares = self.get_shares_owned()
        wealth = 0
        for s in shares:
            wealth = wealth + s.volume * s.athlete.get_value()

        # logger.info("Wealth: " + str(wealth))

        return wealth

    @property
    def share_value(self):
        return self.get_shares_wealth()

    @property
    def total_value(self):
        return self.share_value + self.capital

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

    def get_shares_owned(self):
        shares = Share.objects.filter(owner=self, is_virtual=False, season=get_current_season())
        # logger.info("shares owned: " + str(shares))
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

    def transfer_cash_to(self, ammount, to, reason=None):
        """ Transfer cash from this entity to another
        """
        if self.capital < ammount:
            raise InsufficientFunds(
                "Capital ({}) is less than the transfer ammount ({})".format(
                    self.capital, ammount
                )
            )

        self.capital = self.capital - ammount
        to.capital = to.capital + ammount

        trans = TransactionHistory(
            sender=self, recipient=to, ammount=ammount, reason=reason, season=get_current_season()
        )
        trans.save()
        self.save()
        to.save()

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
    def to_html(self):
        if self.is_investor():
            # return self.investor.display_name
            return '<span class="badgeContainer"><a href="/investor/' + str(self.id) + '" class="badge badge-primary">' + self.investor.display_name + '</a></span>'
        else:
            return self.bank.name

    def is_bank(self):
        try:
            b = self.bank
            return True
        except Bank.DoesNotExist:
            return False

    def __str__(self):
        if self.is_investor():
            return self.investor.__str__()
        elif self.is_bank():
            return self.bank.__str__()
        else:
            return "Entity with capital {}".format(capital)

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


class Investor(Entity):
    """
    An investor is an individual who trades stuff
    """

    LIGHT = "L"
    DARK = "D"
    OXFORD = "O"
    CAMBRIDGE = "C"
    THEMES = (
        (LIGHT, "Light"),
        (DARK, "Dark"),
        (OXFORD, "Oxford"),
        (CAMBRIDGE, "Cambridge"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    uitheme = models.CharField(max_length=1, choices=THEMES, default=LIGHT)

    def __str__(self):
        return "{} ({})".format(self.display_name, self.capital)

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
        # return self.name
        return '<span class="badgeContainer"><a href="/athlete/' + str(self.id) + '" class="badge badge-danger">' + self.name + '</a></span>'

    def serialize(self, investor: Investor =None):
        s = {"id": self.pk, "name": self.name}

        if investor:
            shares = investor.saleable_shares_in_athlete(self)
            vol = 0
            if shares:
                vol = shares.volume
            s["vol_owned"] = vol

        return s

    def get_all_trades(self):
        trades = (
            Trade.objects.all()
            .filter(asset__share__athlete=self, status=Trade.ACCEPTED, season=get_current_season())
            .order_by("updated")
        )
        return trades

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

    def get_value(self, time=None):
        """ Get value of this athlete at some point in time """
        if not time:
            time = current_time()
        # Get all trades for this athlete before this time which were accepted
        trades = Trade.objects.all().filter(
            asset__share__athlete=self, status=Trade.ACCEPTED, season=get_current_season()
        )  # .order_by('updated')
        # Also filter and sort by time
        trades = sorted(
            [t for t in trades if t.updated <= time],
            key=lambda t: t.updated,
            reverse=True,
        )  # more recent dates at the front

        if len(trades) == 0:
            return np.nan

        latest_trade = trades[0]

        # Volume weighted average
        # av = Athlete.compute_value_from_trades(trades)
        # logger.info("Average of {} trades = {}".format(len(trades), av))
        vol = latest_trade.asset.share.volume
        if vol == 0:
            if latest_trade.price != 0.0:
                logger.info("Warning! Trade with 0 volume: {}".format(latest_trade))
            value = 0
        else:
            value = latest_trade.price / vol
        return value

    def get_total_volume_of_shares(self):
        shares = Share.objects.filter(athlete=self, season=get_current_season())
        volume = np.sum(np.array([float(s.volume) for s in shares]))
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
            except Exception:
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

    owner = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_owner",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    is_virtual = models.BooleanField(
        default=False
    )  # need ability to create virtual commodities for an open buy trade
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def serialize(self):
        if self.is_share():
            return self.share.serialize()
        elif self.is_future():
            return self.contract.future.serialize()
        elif self.is_option():
            return self.contract.future.option.serialize()
        elif self.is_swap():
            return self.contract.swap.serialize()
        else:
            logger.info("Trying to serialize unknown asset type!")
            logger.info(self)
            return {"owner": self.owner.serialize(), "virtual": self.is_virtual}

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
        except Future.DoesNotExist:
            return False
        # except Exception:
        #     return False
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
        if not (self.is_contract() and self.is_future()):
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
            val = "Asset owned by {}".format(self.owner)
            if self.is_virtual:
                val = val + " (virtual)"
            return val


class Share(Asset):
    """
    Most common type of asset - a share in an athlete
    """

    athlete = models.ForeignKey(
        Athlete,
        related_name="%(app_label)s_%(class)s_athlete",
        on_delete=models.CASCADE,
    )
    volume = models.FloatField()

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
    """ A contract is a type of asset which is a contract between two parties
    We assume that one party is the Asset.owner, and the other is "other_party" below
    There is nothing special about being the owner vs being the other_party 
    
    future, options, and swaps are all contracts. They are also all assets. """
    other_party = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_other_party",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    def __str__(self):
        return "{} contract between {} and {}".format(self.contract_type, self.owner.print_name, self.other_party.print_name)
    
    @property
    def value(self):
        """ This should be overriden """
        if self.is_future():
            return self.future.value
        return np.nan

    @property
    def contract_type(self):
        return self.asset_type


    def get_obligation(self, investor):
        if self.owner == investor:
            return self.future.owner_obligation
        else:
            if self.future.owner_obligation == Future.BUY:
                return Future.SELL
            return Future.BUY


    def get_other_party_to(self, investor):
        if self.owner == investor:
            return self.other_party
        return owner


class Future(Contract):
    """ An agreement to buy/sell in the future at a fixed price """

    strike_price = models.FloatField()
    action_date = models.DateTimeField()

    # Assume underlying asset is a share for now - otherwise this gets very complicated
    underlying_asset = models.ForeignKey(Share, on_delete=models.CASCADE)

    SELL = "S"
    BUY = "B"
    OBLIGATIONS = (
        (BUY, "Buy"),
        (SELL, "Sell"),
    )

    owner_obligation = models.CharField(max_length=1, choices=OBLIGATIONS, default=BUY)

    settled = models.BooleanField(default=False)

    def __str__(self):
        return "Future: Owner({}) to {} ({}, {}) from/to {} for {} at {}".format(self.owner,self.obligation, self.underlying_asset.athlete.name,
        self.underlying_asset.volume, self.other_party, self.strike_price, self.action_date)

    def serialize(self):
        s = {"id": self.pk,
            "underlying": self.underlying_asset.serialize(),
        "strike_price": self.strike_price,
        "strike_date": self.action_date,
        "owner_obligation": self.obligation,
        "owner": serialize_entity(self.owner),
        "other_party": serialize_entity(self.other_party),
        }

        return s

    @property
    def value(self):
        """ value of futures contract is strike_price - current_price 
        TODO 
        """
        current_price_per_share = self.underlying_asset.athlete.get_value()
        current_price = current_price_per_share*self.underlying_asset.volume

        logging.info("Current price: {} ({} per share, vol={}) for future id: {}".format(current_price, current_price_per_share, self.underlying_asset.volume, self.id))
        return current_price - self.strike_price

    @property
    def obligation(self):
        # return self.owner_obligation
        dictionary = dict(self.OBLIGATIONS)
        try:
            v = dictionary[self.owner_obligation]
        except KeyError:
            logger.warning("owner obligation: {} doesn't match expected values for future id: {}".format(self.owner_obligation, self.id))
            v = self.owner_obligation

        return v
        # return dict(self.OBLIGATIONS)[self.owner_obligation]

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
    owner = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_owner",
        on_delete=models.CASCADE,
    )
    other_party = models.ForeignKey(
        Entity,
        related_name="%(app_label)s_%(class)s_other_party",
        on_delete=models.CASCADE,
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    # value = models.FloatField()

    def __str__(self):
        return "{} contract between {} and {} ({})".format(self.contract.contract_type, self.owner.print_name, self.other_party.print_name, self.timestamp)


class Option(Future):
    """ An option is a future where one party has the option to go through with the trade or not """

    # Note that banks cannot hold options, only investors
    # option_holder = models.ForeignKey(Investor, related_name="%(app_label)s_%(class)s_option_holder", on_delete=models.CASCADE)
    # option holder is just the owner
    current_option = models.BooleanField(
        default=True
    )  # whether to conduct trade, can be change by the option holder

    def serialize(self):
        s =  {"id": self.pk, "underlying": self.underlying_asset.serialize(),
        "strike_price": self.strike_price,
        "strike_date": self.action_date,
        "current_option": self.current_option,
         "buyer": serialize_entity(self.buyer),
        "seller": serialize_entity(self.seller),}

        # if self.owner:
        #     s["owner"] = serialize_entity(self.owner)

        return s

@background(schedule=0)
def settle_future(future_id):
    """ To call:
    settle_future(future, schedule=future.action_date)
    """

    logging.info("Settle future with id: {}".format(future_id))
    future = Future.objects.get(pk=future_id)

    if future.settled:
        logging.info("Already settled")
        return

    # Now we try and transfer the underlying asset
    # What to do if one party doesn't have the shares or cash to fulfill deal?
    # Abort - one or both parties default, and owe a debt of the 2*future value

    if future.owner_obligation == Future.SELL:
        seller = future.owner
        buyer = future.other_party
    else:
        seller = future.other_party
        buyer = future.owner

    seller_has_shares =  seller.can_sell_asset(future.underlying_asset)
    buyer_has_cash = buyer.capital >= future.strike_price

    if seller_has_shares and buyer_has_cash:
        
        # Do the transfer by creating and immediately accepting a share trade
        t = Trade.make_share_trade(future.underlying_asset.athlete, vol, seller, future.strike_price, seller, buyer)
        t.accept_trade(action_by=buyer, skip_notif=True)

        # share = seller.get_share(future.underlying_asset)
        # vol = future.underlying_asset.volume
        # share.transfer(to=buyer, vol=vol)
        # buyer.transfer_cash_to(ammount=future.strike_price, to=seller, reason="Future trade: " + str(future))

        future.settled = True
        future.save()

        # Send notifications
        common = "{:.2f} shares in {} for {:.2f} per share".format(vol, share.athlete.name, future.strike_price/vol)
        
        Notification.send_notification(title="Future contract settled", description="You bought " + common, entity=buyer)
        Notification.send_notification(title="Future contract settled", description="You sold" + common, entity=seller)
        
    else:
        print("Unable to settle futures contract")

        # # format(seller.saleable_shares_in_athlete())
        # raise InsufficientShares(
        #     "Seller ({}) does not have sufficient shares to fulfill trade.".format(seller.print_name)
        # )
    

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
        return {"id": self.pk}


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

    price = models.FloatField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    decision_dt = models.DateTimeField(blank=True, null=True)
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
            "decision_dt": self.decision_dt,
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
            raise InsufficientFunds("Trade price exceeds your capital")

        if seller and creator == seller:
            s = seller.saleable_shares_in_athlete(athlete)
            if not s or s.volume < volume:
                raise InsufficientShares(
                    "You do not have this many shares available to sell"
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
    def make_option_trade(athlete, volume, creator, price, seller, buyer, strike_date, strike_price, holder, future_buyer, future_seller):
        # Trade.check_share_trade_possible(buyer, seller, creator, price, volume, athlete)

        # virtual_share = Share(
        #     athlete=athlete, volume=volume, is_virtual=True, season=get_current_season()
        # )
        # virtual_share.save()

        # option = Option(underlying_asset=virtual_share, action_date=strike_date, strike_price=strike_price, buyer=future_buyer, seller=future_seller)

        # trade = Trade.make_trade(option, creator, price, seller, buyer)
        # return trade
        return None


    @staticmethod
    def make_future_trade(athlete, volume, creator, price, seller, buyer, strike_date, strike_price, owner_obligation):
        Trade.check_share_trade_possible(buyer, seller, creator, price, volume, athlete)

        virtual_share = Share(
            athlete=athlete, volume=volume, is_virtual=True, season=get_current_season()
        )
        virtual_share.save()

        future = Future(underlying_asset=virtual_share, action_date=strike_date, strike_price=strike_price, 
        season=get_current_season(), owner_obligation=owner_obligation, owner=buyer, other_party=seller)
        future.save()
        
        trade = Trade.make_trade(asset=future, creator=creator, price=price, seller=seller, buyer=buyer)
        return trade

    @staticmethod
    def make_swap_trade(investor, price, seller, buyer, swap_details):
        pass

    def make_trade(asset, creator, price, seller=None, buyer=None):
        price = np.round(price, 2)  # ensure price is always to 2 DP
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

    def accept_trade(self, action_by, skip_notif=False):
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
        if self.asset.is_share():
            if not self.seller.can_sell_asset(self.asset):
                # format(seller.saleable_shares_in_athlete())
                raise InsufficientShares(
                    "Seller ({}) does not have sufficient shares to fulfill trade.".format(self.seller.print_name)
                )

            # Do the trade
            logger.info(
                "Accepted trade: {}".format(self)
            )  
            share = self.seller.get_share(self.asset.share)
            share.transfer(to=self.buyer, vol=self.asset.share.volume)
            # self.status = self.ACCEPTED
            # self.save()

            # Send notification to not actioner
            

            common = "Share: {} ({}) for {}".format(self.asset.share.athlete.name, self.asset.share.volume, self.price)
            Notification.send_notification(title="Trade accepted", description="{} accepted the trade for {}".format(action_by, common), entity=other_party)
            

        elif self.asset.is_future():
            # Only one check to perform - can purchaser of contract pay the trade price?
            # This is already done.
            
            # 1) Confirm contract
            # The future owner is the buyer of the contract
            self.asset.owner = self.buyer
            self.asset.contract.future.other_party = self.seller
            self.asset.contract.future.save()
            self.asset.save()

            # 2) Schedule settlement action
            # settle_future(future, schedule=future.action_date)
            # For testing, just schedule 5 seconds in the future
            if settings.TESTING_FUTURES_TIMING > 0:
                schedule = settings.TESTING_FUTURES_TIMING
            else:
                schedule = self.asset.contract.future.action_date
            settle_future(self.asset.contract.future.pk, schedule=schedule)


            fut = self.asset.contract.future
            common = "Future: (Owner to {} {} shares in {} for {}). Trade price: {}".format(fut.owner_obligation, fut.underlying_asset.volume, fut.underlying_asset.athlete.name, fut.strike_price, self.price)
            Notification.send_notification(title="Trade accepted", description="{} accepted the trade for asset: {}".format(action_by, common), entity=other_party)
            
          
        else:
            logger.info("Unable to complete trade for {}".format(self.asset))
            return

        b = self.buyer
        b.transfer_cash_to(ammount=self.price, to=self.seller, reason="Share trade: " + str(self))

        self.seller.save()
        self.buyer.save()

        self.status = self.ACCEPTED
        self.save()


@receiver(pre_save, sender=Trade)
def update_on_trade_acceptance(sender, instance, **kwargs):
    """ Update indexes rating """
    
    if instance.id:
        old_trade = Trade.objects.get(pk=instance.id)
        if old_trade.status == Trade.PENDING and instance.status == Trade.ACCEPTED:
            # Recompute top 10 index
            schedule_share_calculation()

            if instance.asset.is_contract():

                if instance.asset.is_future():
                    other_party = instance.asset.contract.future.other_party
                    
                elif instance.asset.is_option():
                    other_party = instance.asset.option.other_party
                elif instance.asset.is_swap():
                    other_party = instance.asset.swap.other_party

                c = ContractHistory(owner=instance.asset.owner, 
                other_party=instance.asset.contract.other_party, contract=instance.asset.contract)
                c.save()
            

@background(schedule=5)
def schedule_share_calculation():
    """ Compute shares indexes in 5 seconds time """
    ShareIndexValue.compute_value(ShareIndexValue.TOP10)


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
    interest_rate = models.FloatField()

    # How much needs to be repayed
    balance = models.FloatField()

    # Default interval is weekly
    repayment_interval = models.DurationField(default=timedelta(days=7))

    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def serialize(self):
        return {
            "lender": self.lender.serialize(),
            "recipient": self.recipient.serialize(),
            "created": self.created,
            "last_processed": self.last_processed,
            "next_payment_due": self.next_payment_due,
            "interest_rate": self.interest_rate,
            "balance": self.balance,
            "repayment_interval": self.repayment_interval,
        }

    def __str__(self):
        return "Loan of {} from {} to {}".format(
            self.balance, self.lender, self.recipient
        )

    def create_loan(lender, recipient, interest, balance, interval):

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
        )
        lender.transfer_cash_to(balance, recipient, reason="Loan created: " + str(loan))

        # Create recurring payment schedule here
        # TODO

        lender.save()
        recipient.save()
        loan.save()

    def pay_interest(self):

        # Check if it is indeed time to repay - is this approximately the time that the next repayment is due?
        diff = current_time() - self.next_payment_due
        if not np.abs(diff.seconds) < np.abs(self.repayment_interval.seconds) / 10.0:
            return

        if self.balance == 0:
            return

        interest_ammount = np.round(self.interest_rate * self.balance, 2)
        logger.info(
            "Pay interest {} from {} to {}".format(
                interest_ammount, self.recipient, self.lender
            )
        )

        if self.recipient.capital > interest_ammount:

            self.recipient.transfer_cash_to(
                interest_ammount, self.lender, reason="Loan interest payment: " + str(self)
            )

        else:
            ammount_payable = self.recipient.capital

            # self.lender.capital = self.lender.capital + ammount_payable
            # self.recipient.capital = 0
            self.recipient.transfer_cash_to(
                ammount_payable, self.lender, reason="Loan interest payment: " + str(self)
            )

            # Create new debt
            debt = Debt(
                owed_by=self.recipient,
                owed_to=self.lender,
                ammount=interest_ammount - ammount_payable,
            )
            debt.save()

        self.last_processed = current_time()
        self.next_payment_due = self.last_processed + self.repayment_interval

        self.lender.save()
        self.recipient.save()
        self.save()

    def repay_loan(self, ammount):
        self.recipient.transfer_cash_to(ammount, self.lender, reason="Loan repayment: "+ str(self))


def pay_all_loans():
    loans = (
        Loan.objects.all()
        .filter(next_payment_due__lte=current_time(),season=get_current_season())
        .exclude(balance=0)
    )

    for l in loans:
        l.pay_interest()


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

    ammount = models.FloatField()

    def serialize(self):
        return {
            "owed_by": self.owed_by.serialize(),
            "owed_to": self.owed_to.serialize(),
            "created": self.created,
            "ammount": self.ammount,
        }


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
    ammount = models.FloatField()
    reason = (
        models.TextField()
    )  # e.g. buying volume of shares from X, repaying loan to X
    timestamp = models.DateTimeField(auto_now_add=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

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
    max_dividend = models.FloatField()
    min_dividend = models.FloatField(default=10.0)
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
            "max_dividend": self.max_dividend,
            "min_dividend": self.min_dividend,
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
    dividend = models.FloatField(null=True, blank=True)
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
    volume = models.FloatField()
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE)

    def __str__(self):
        return "{} ({})".format(self.athlete.name, np.round(self.volume, 2))

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
    volume = models.FloatField()
    price_per_volume = models.FloatField()

    class Meta:
        # Each bidder can only have one bid on a lot
        unique_together = ('bidder', 'lot',)

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


def compute_dividends(race: Race):
    if not race.num_competitors:
        return

    results = Result.objects.all().filter(race=race)
    for r in results:
        scaled_position = (
            race.num_competitors - (r.position - 1)
        ) / race.num_competitors
        r.dividend = np.round(
            race.min_dividend
            + (race.max_dividend - race.min_dividend) * pow(scaled_position, 2),
            2,
        )
        r.save()


def cowley_club_bank():
    bank = Bank.objects.get(name="The Cowley Club Bank")
    return bank
