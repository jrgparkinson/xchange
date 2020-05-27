from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta, datetime
import pytz
import numpy as np
from app.errors import * 
from django.db.models import Q


class Season(models.Model):

    OPEN = 'O'
    SUSPENDED = 'S'
    STATUS_CHOICES = (
        (OPEN, 'Open'),
        (SUSPENDED, 'Suspended'),
    )

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=OPEN)
    name = models.CharField(max_length=100)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

def current_time():
    return datetime.now(pytz.utc)

def get_current_season():
    return Season.objects.get(status=Season.OPEN)

def format_currency(currency):
    locale.setlocale( locale.LC_ALL, '' )
    currency_str = locale.currency( currency, grouping=True ) + "M"
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
        if self.is_bank():
            return self.bank.serialize()
        elif self.is_investor():
            return self.investor.serialize()
        else:
            return {"capital": self.capital}

    

    def get_capital(self, time):
        current_capital = self.capital

        # Transactions for this entity
        cash_transactions = TransactionHistory.objects.all().filter((Q(sender=self) | Q(recipient=self)) & Q(timestamp_gte=time))

        # Add/remove cash to get back to point in time we care about
        for t in cash_transactions:
            if t.sender == self:
                current_capital = current_capital-  t.ammount

            else:
                current_capital = current_capital + t.ammount

        return current_capital

    def get_portfolio_values(self):
        cash_transactions = TransactionHistory.objects.all().filter((Q(sender=self) | Q(recipient=self))).order_by('timestamp')
        this_time = current_time()
        # cash_transactions = sorted(cash_tra)

        # Start of the season
        investor_capital = self.INITIAL_CAPITAL
        cash_positions = [{"time": round_time(get_current_season().start_time), "value": investor_capital, "type": "cash"}]

        for t in cash_transactions:

            # If this investor sent the money, then return state to before this (add money)
            if t.sender == self:
                investor_capital = investor_capital - t.ammount
            else:
                investor_capital = investor_capital + t.ammount

            cash_positions.append({"time": round_time(t.timestamp), "value": investor_capital, "type": "cash"})

        if not self.capital == investor_capital:
            print("ERROR computing capital! {} != {}".format(self.capital, investor_capital))
            # raise XChangeException("Internal inconsistency in determing cash content of portfolio value")

        cash_positions.append({"time": round_time(this_time), "value": self.capital, "type": "cash"})
            

        share_transactions = Trade.objects.all().filter(status=Trade.ACCEPTED).order_by('updated')
        investor_shares = {}
        
        # Assume everyone starts with 0 shares
        share_positions = []

        share_positions.append({"time": round_time(get_current_season().start_time), "value": 0.0, "type": "share"})

        # Now for each share transaction, re compute
        for t in share_transactions:
            share = t.asset.share
            athlete = share.athlete

            # investor bought share, return state to before this
            # by subtracting volume of shares
            if not athlete.name in list(investor_shares.keys()):
                investor_shares[athlete.name] = {"vol": 0}

            if share.volume == 0:
                print("Share has zero volume: {}".format(share))
            else:
                investor_shares[athlete.name]["val"] = t.price/share.volume

            if t.buyer == self:
                investor_shares[athlete.name]["vol"] = investor_shares[athlete.name]["vol"] + share.volume

            # If the investor sold the share at this point, re add it to the 
            elif t.seller == self: 
                investor_shares[athlete.name]["vol"] = investor_shares[athlete.name]["vol"] - share.volume

            total_share_val = 0
            for athlete, share in investor_shares.items():
                total_share_val = total_share_val + share["vol"] * share["val"]
            
            share_positions.append({"time": round_time(t.updated), "value": total_share_val, "type": "share"})
        
        share_positions.append({"time": round_time(this_time), "value": total_share_val, "type": "share"})

        # current_share_value = 

        # Now the trick is to combine them
        
        all_positions = share_positions + cash_positions
        all_positions = sorted(share_positions + cash_positions, key=lambda t: t["time"])
        # print(all_positions)

        # all_positions_merged = []
        records_expected_per_time = {}
        records_processed_per_time = {}
        for time in list(set([t["time"] for t in all_positions])):
            all_for_time = [t for t in all_positions if t["time"] == time]
            # print("Found {} records for time = {}".format(len(all_for_time), time))
            records_expected_per_time[time.timestamp()] = len(all_for_time)
            records_processed_per_time[time.timestamp()] = 0 

        
        combined_total = []
        running_cash = 0
        running_shares = 0
        for t in all_positions:
            if t["type"] == "cash":
                running_cash = t["value"]
            elif t["type"] == "share":
                running_shares = t["value"]

            records_processed_per_time[t["time"].timestamp()] = records_processed_per_time[t["time"].timestamp()] + 1
            if records_processed_per_time[t["time"].timestamp()] == records_expected_per_time[t["time"].timestamp()]:
                combined_total.append({"time": t["time"], "value": running_cash + running_shares})

        return {"combined": combined_total, "cash": cash_positions, "shares": share_positions}  # cash_positions

         
    def get_shares_wealth(self):
        """ Get entities current share holding value """
        shares = self.get_shares_owned()
        wealth = 0
        for s in shares:
            wealth = wealth + s.volume * s.athlete.get_value()

        return wealth

    @property
    def share_value(self):
        return self.get_shares_wealth()
    
    def get_share_vol(self, athlete, time):
        current_shares = self.shares_in_athlete(athlete)

        vol = 0
        if current_shares:
            vol = current_shares.volume

        trades = Trade.objects.all().filter((Q(buyer=self) | Q(seller=self)) & Q(status=Trade.ACCEPTED) & Q(updated_gte=time))
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
        return Share.objects.filter(owner=self, is_virtual=False)     

    def shares_in_athlete(self, athlete):
        try:
            share = Share.objects.get(owner=self, is_virtual=False, athlete=athlete)
            # print("Share for {}: {}".format(self, share))
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
            # print("Shares for {}: {}".format(self, str(shares)))
            # return None

    def get_share(self, share):
        try:
            share = Share.objects.get(owner=self, is_virtual=False, athlete=share.athlete)
            return share
        except Share.DoesNotExist:
            return None

    def transfer_cash_to(self, ammount, to, reason=None):
        """ Transfer cash from this entity to another
        """
        if self.capital < ammount:
            raise InsufficientFunds
    
        self.capital = self.capital - ammount
        to.capital = to.capital + ammount

        trans = TransactionHistory(sender=self, recipient=to, ammount=ammount, reason=reason)
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
            return self.investor.user.username
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
        if not (isinstance(other, Entity) or isinstance(other, Investor) or isinstance(other, Bank)):
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
        return {"name": self.name,
        "capital": self.capital}

class Investor(Entity):
    """
    An investor is an individual who trades stuff
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    

    def __str__(self):
        return "{} ({})".format(self.user.username, self.capital)

    def __repr__(self):
        return self.user.username

    def serialize(self):
        return {"id": self.pk,
        "name": self.user.username,
            "capital": self.capital}


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Investor.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.investor.save()

class Club(models.Model):
    name = models.CharField(max_length=100, unique=True)

class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    club = models.ForeignKey(Club, on_delete=models.CASCADE)

class Athlete(models.Model):
    """
    An athlete who earns dividends for their share holders
    """
    VALUE_AVERAGE_SIZE = 3

    name = models.CharField(max_length=100, unique=True)
    power_of_10 = models.URLField()
    club = models.ForeignKey(Club, on_delete=models.CASCADE)
    team_last_year = models.ForeignKey(Team, on_delete=models.CASCADE, null=True)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name

    def serialize(self):
        return {"id": self.pk, "name": self.name}

    def get_all_trades(self):
        trades = Trade.objects.all().filter(asset__share__athlete=self, status=Trade.ACCEPTED).order_by('updated')
        return trades

    def get_historical_value(self):
        # Worried this retrieve might end up being very slow
        # trades = Trade.objects.all().filter(status=Trade.ACCEPTED).order_by('updated')
        trades = self.get_all_trades()
        # trades = [t for t in trades if t.asset.is_share() and t.asset.share.athlete == self]
        
        print("Found {} trades for athlete".format(len(trades)))
        # print(trades)
        # values = []
        # for i in range(Athlete.VALUE_AVERAGE_SIZE, len(trades)):
        #     trades_to_consider = trades[i-Athlete.VALUE_AVERAGE_SIZE: i]
        #     v = Athlete.compute_value_from_trades(trades_to_consider)
        #     latest_time = trades[i].updated
        #     print("Average of {} to {} ({} trades) = {}".format(i-Athlete.VALUE_AVERAGE_SIZE, i, len(trades_to_consider), v))
        #     values.append({"time": latest_time, "value": v})
        values = [{"time": t.updated, "value": t.price/t.asset.share.volume} for t in trades]

        # print(values)
        return values

    
    def compute_value_from_trades(trades):
        # note that t.price is the price for the full volume, 
        # to t.price = price per volume * volume
        average = np.sum(np.array([t.price for t in trades])) / np.sum(np.array([t.asset.share.volume for t in trades]))

        # Just use most recent trade
        trades = sorted(trades, key=lambda t: t.updated, reverse=True) 
        for t in trades:
            print("Trade on {}".format(t.updated))
        trade = trades[0]
        value = trade.price/trade.asset.share.volume
        # print("Most recent data: {}".format(trade.updated))

        return value

    def get_value(self, time=None):
        """ Get value of this athlete at some point in time """
        if not time:
            time = current_time()
        # Get all trades for this athlete before this time which were accepted
        trades = Trade.objects.all().filter(asset__share__athlete=self, status=Trade.ACCEPTED) #.order_by('updated')
        # Also filter and sort by time
        trades = sorted([t for t in trades if t.updated <= time], key=lambda t: t.updated, reverse=True) # more recent dates at the front

        if len(trades) == 0:
            return np.nan

        latest_trade = trades[0]
        
        # Volume weighted average
        # av = Athlete.compute_value_from_trades(trades)
        # print("Average of {} trades = {}".format(len(trades), av))
        value = latest_trade.price / latest_trade.asset.share.volume
        return value

    def get_total_volume_of_shares(self):
        shares = Share.objects.filter(athlete=self)
        volume = np.sum(np.array([float(s.volume) for s in shares]))
        return volume

class Asset(models.Model):
    """
    Something that can be bought and sold
    A virtual asset is one involved in an open trade
    
    The owner can be null if it is a virtual asset
    
    """
    
    owner = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owner", on_delete=models.CASCADE, blank=True, null=True)
    is_virtual = models.BooleanField(default=False) # need ability to create virtual commodities for an open buy trade
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def serialize(self):
        if self.is_share():
            return self.share.serialize()
        else:
            return {"owner": self.owner,
            "virtual": self.is_virtual}

    def is_share(self):
        try:
            share = self.share
        except Share.DoesNotExist:
            return False
        return True

    def __str__(self):
        if self.is_share():
            return self.share.__str__()
        else:
            val = "Asset owned by {}".format(self.owner)
            if self.is_virtual:
                val = val + " (virtual)"
            return val

class Share(Asset):
    """
    Most common type of asset - a share in an athlete
    """

    athlete = models.ForeignKey(Athlete, related_name="%(app_label)s_%(class)s_athlete", on_delete=models.CASCADE)
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
            return {"id": self.pk,
            "owner": self.owner,
            "virtual": self.is_virtual,
            "athlete": self.athlete.serialize(),
            "volume": self.volume}


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
            new_share = Share(athlete=self.athlete, volume=vol, owner=self.owner,season=self.season)
            new_share.save()
            return new_share


    
class Future(Asset):
    """ An agreement to buy/sell in the future at a fixed price """

    strike_price = models.FloatField()
    action_date = models.DateTimeField()

class Option(Future):
    """ An option is a future where one party has the option to go through with the trade or not """

    # Note that banks cannot hold options, only investors
    # option_holder = models.ForeignKey(Investor, related_name="%(app_label)s_%(class)s_option_holder", on_delete=models.CASCADE)
    # option holder is just the owner
    current_option = models.BooleanField(default=True)  # whether to conduct trade, can be change by the option holder

class Swap(Asset):
    """ A swap is an agreement for two parties to pay each other
    some ammount at regular intervals based on two different metrics 
    e.g. A pays B 5% of 10million per week
    B pays A 5% of the value of some share each week 
    
    If the value of the share goes up, B loses money
    If the value of the share goes down, B makes money
    
    This is quite complicated, not properly implemented yet """

    party_a = models.ForeignKey(Investor, related_name="%(app_label)s_%(class)s_partya", on_delete=models.CASCADE)
    party_b = models.ForeignKey(Investor, related_name="%(app_label)s_%(class)s_partyb", on_delete=models.CASCADE)

    # These are essentially an equation, could be quite complicated to implement
    a_to_b_payment = models.TextField()
    b_to_a_payment = models.TextField()

class Trade(models.Model):
    """ 
    Transfer of a asset between two entities.
    Typically investor to investor
    """

    PENDING = 'P'
    ACCEPTED = 'A'
    REJECTED = 'R'
    CANCELLED = 'C'
    STATUS_CHOICES = (
        (PENDING, 'Pending'),
        (ACCEPTED, 'Accepted'),
        (REJECTED, 'Rejected'),
        (CANCELLED, 'Cancelled'),
    )

    asset = models.ForeignKey(Asset, related_name="%(app_label)s_%(class)s_asset", on_delete=models.CASCADE)

    seller = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_seller", on_delete=models.CASCADE, blank=True, null=True)
    buyer = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_buyer", on_delete=models.CASCADE, blank=True, null=True)

    # Who initiated the trade (offered to sell/asked to buy)?
    creator = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_creator", on_delete=models.CASCADE)

    price = models.FloatField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    decision_dt = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=PENDING)

    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def __str__(self):
        return "{} from {} to {} for {} ({})".format(self.asset, self.seller, self.buyer, self.price, self.status)

    def serialize(self):
        json = {"id": self.pk,
        "asset": self.asset.serialize(),
        "creator": self.creator.serialize(),
        "price": self.price,
        "created": self.created,
        "updated": self.updated,
        "status": dict(self.STATUS_CHOICES)[self.status],
        "decision_dt": self.decision_dt}

        if self.buyer:
            json["buyer"] = self.buyer.serialize()
        if self.seller:
            json["seller"] = self.seller.serialize()

        return json

    def make_share_trade(athlete, volume, creator, price, seller: Investor =None, buyer=None):
        # Check this is possible!
        if buyer and creator == buyer and price > buyer.capital:
            raise InsufficientFunds("Trade price exceeds your capital")

        if seller and creator == seller:
            s = seller.saleable_shares_in_athlete(athlete)
            if not s or s.volume < volume:
                raise InsufficientShares("You do not have this many shares available to sell")


        virtual_share = Share(athlete=athlete, volume=volume, is_virtual=True,season=get_current_season())
        virtual_share.save()

        trade = Trade.make_trade(virtual_share, creator, price, seller, buyer)
        return trade

    def make_trade(asset, creator, price, seller=None, buyer=None):
        price = np.round(price, 2) # ensure price is always to 2 DP
        trade = Trade(asset=asset, seller=seller, buyer=buyer, 
        creator=creator, price=price, status=Trade.PENDING,season=get_current_season())
        trade.save()
        return trade

    @property
    def status_display(self):
        return dict(self.STATUS_CHOICES)[self.status]

    def reject_trade(self):
        if not self.status == self.PENDING:
            raise TradeNotPending(desc="Status of trade is {}".format(self.status_display))

        self.status=self.REJECTED
        self.save()

    def cancel_trade(self):
        if not self.status == self.PENDING:
            raise TradeNotPending(desc="Status of trade is {}".format(self.status_display))

        self.status = self.CANCELLED
        self.save()

    def accept_trade(self, action_by):
        if not self.buyer or not self.seller:
            raise NoBuyerOrSeller

        if not self.status == self.PENDING:
            raise TradeNotPending
        
        # Check action_by can do this - we must not be the creator
        if action_by == self.creator:
            print("Trade creator = {}".format(self.creator))
            print("Action by = {}".format(action_by))
            raise NoActionPermission

        # Check buyer has cash
        if not self.buyer.capital >= self.price:
            raise InsufficientFunds

        # Check seller has asset to sell
        if self.asset.is_share():
            if not self.seller.can_sell_asset(self.asset):
                raise InsufficientShares

            # Do the trade
            print("Accepted trade: {}".format(self)) #  for {} from {} to {}".format(self.asset, self.seller, self.buyer))
            # print(" Before, seller ({}) owns: {}".format(self.seller, self.seller.shares_in_athlete(self.asset.share.athlete)))
            # print(" Before, buyer ({}) owns: {}".format(self.buyer, self.buyer.shares_in_athlete(self.asset.share.athlete)))
            share = self.seller.get_share(self.asset.share)
            share.transfer(to=self.buyer, vol=self.asset.share.volume)
            self.status = self.ACCEPTED
            self.save()

            # Transfer cash if all successful (have already confirmed the cash is available to transfer)
            b = self.buyer
            b.transfer_cash_to(ammount=self.price, to=self.seller, reason=str(self))

            self.seller.save()
            self.buyer.save()

            # print(" After, seller ({}) owns: {}".format(self.seller, self.seller.shares_in_athlete(self.asset.share.athlete)))
            # print(" After, buyer ({}) owns: {}".format(self.buyer, self.buyer.shares_in_athlete(self.asset.share.athlete)))

            

        else:
            print("Unable to complete trade for {}".format(self.asset))
            return



class Loan(models.Model):
    """ One entity may loan another entity some capital, which is repayed at some interest rate
    """
    lender = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_lender", on_delete=models.CASCADE, blank=False, null=False)
    recipient = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_recipient", on_delete=models.CASCADE, blank=False, null=False)

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
        return {"lender": self.lender.serialize(),
        "recipient": self.recipient.serialize(),
        "created": self.created,
        "last_processed": self.last_processed,
        "next_payment_due": self.next_payment_due,
        "interest_rate": self.interest_rate,
        "balance": self.balance,
        "repayment_interval": self.repayment_interval}

    def __str__(self):
        return "Loan of {} from {} to {}".format(self.balance, self.lender, self.recipient)

    def create_loan(lender, recipient, interest, balance, interval):

        # Perform checks
        # Can't lend money you don't have
        if lender.capital < balance:
            raise InsufficientFunds

        
        next_payment_due = current_time() + interval
        loan = Loan(lender=lender, recipient=recipient, interest_rate=interest, 
                    balance=balance, repayment_interval=interval, next_payment_due=next_payment_due)
        lender.transfer_cash_to(balance, recipient, reason=str(loan))

        # Create recurring payment schedule here
        # TODO

        lender.save()
        recipient.save()
        loan.save()

    def pay_interest(self):

        # Check if it is indeed time to repay - is this approximately the time that the next repayment is due?
        diff = current_time() - self.next_payment_due
        if not np.abs(diff.seconds) < np.abs(self.repayment_interval.seconds)/10.0:
            return

        if self.balance == 0:
            return

        interest_ammount = np.round(self.interest_rate * self.balance, 2)
        print("Pay interest {} from {} to {}".format(interest_ammount, self.recipient, self.lender))

        if self.recipient.capital > interest_ammount:

            self.recipient.transfer_cash_to(interest_ammount, self.lender, reason=str(self))

        else:
            ammount_payable = self.recipient.capital

            # self.lender.capital = self.lender.capital + ammount_payable
            # self.recipient.capital = 0
            self.recipient.transfer_cash_to(ammount_payable, self.lender, reason=str(self))

            # Create new debt
            debt = Debt(owed_by=self.recipient, owed_to=self.lender, ammount=interest_ammount - ammount_payable)
            debt.save()

        self.last_processed = current_time()
        self.next_payment_due = self.last_processed + self.repayment_interval

        self.lender.save()
        self.recipient.save()
        self.save()

    def repay_loan(self, ammount):
        self.recipient.transfer_cash_to(ammount, self.lender, reason=str(self))



def pay_all_loans():
    loans = Loan.objects.all().filter(next_payment_due__lte=current_time()).exclude(balance=0)

    for l in loans:
        l.pay_interest()

class Debt(models.Model):
    """ Having introduced loans, we must now allow for debt 
    E.g. if someone is unable to pay back a loan
    """
    owed_by = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owed_by", on_delete=models.CASCADE, blank=False, null=False)
    owed_to = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owed_to", on_delete=models.CASCADE, blank=False, null=False)

    created = models.DateTimeField(auto_now_add=True)

    ammount = models.FloatField()

    def serialize(self):
        return {"owed_by": self.owed_by.serialize(),
        "owed_to": self.owed_to.serialize(),
        "created": self.created,
        "ammount": self.ammount}

class TransactionHistory(models.Model):
    """ We should keep a track of all transactions made """
    sender = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_from", on_delete=models.CASCADE, blank=False, null=False)
    recipient = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_to", on_delete=models.CASCADE, blank=False, null=False)
    ammount = models.FloatField()
    reason = models.TextField() # e.g. buying volume of shares from X, repaying loan to X
    timestamp = models.DateTimeField(auto_now_add=True)

    def serialize(self):
        return {"sender": self.sender.serialize(),
        "recipient": self.recipient.serialize(),
        "ammount": self.ammount,
        "reason": self.reason}

class Event(models.Model):
    """ Athletes compete in Events and hence earn dividends """
    name = models.CharField(max_length=100)
    date = models.DateField()
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

    def __str__(self):
        return "{} ({})".format(self.name, self.date.strftime("%d/%m/%Y"))

    def serialize(self):
        return {"name": self.name,
        "date": self.date}

class Race(models.Model):
    """ Many races per event """
    event = models.ForeignKey(Event, related_name="%(app_label)s_%(class)s_event", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    time = models.DateTimeField()
    results_link = models.URLField()
    event_details_link = models.URLField()
    max_dividend = models.FloatField()
    min_dividend = models.FloatField(default=10.0)
    num_competitors = models.IntegerField()

    def __str__(self):
        return "{} ({})".format(self.name, self.time.strftime("%d/%m/%Y %H:%m"))

    def serialize(self):
        return {"event": self.event.serialize(),
        "name": self.name,
        "time": self.time}


class Result(models.Model):
    """ Results are recorded for athletes when they
    perform well in an event.

    They are entered manually by the XChange administrator, and automatically distributed 
    in a proportional manner to those
    who owned shares in the athlete at the start of the event. 
    """
    athlete = models.ForeignKey(Athlete, related_name="%(app_label)s_%(class)s_athlete", on_delete=models.CASCADE)
    race = models.ForeignKey(Race, on_delete=models.CASCADE)
    position = models.IntegerField()
    time = models.DurationField()
    dividend = models.FloatField()
    dividend_distributed = models.BooleanField(default=False)

    def serialize(self):
        return {"athlete": self.athlete.serialize(),
        "event": self.event.serialize(),
        "dividend": self.dividend,
        "dividend_distributed": self.dividend_distributed}



# For dealing with auctions
class Auction(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    season = models.ForeignKey(Season, on_delete=models.CASCADE)

class Lot(models.Model):
    athlete = models.ForeignKey(Athlete, related_name="%(app_label)s_%(class)s_athlete", on_delete=models.CASCADE)
    volume = models.FloatField()

class Bid(models.Model):
    PENDING = 'P'
    ACCEPTED = 'A'
    REJECTED = 'R'
    STATUS_CHOICES = (
        (PENDING, 'Pending'),
        (ACCEPTED, 'Accepted'),
        (REJECTED, 'Rejected'),
    )

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=PENDING)

    bidder = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_bidder", on_delete=models.CASCADE)
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE)
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE)
    volume = models.FloatField()
    price_per_volume = models.FloatField()
    
    
def compute_dividends(race: Race):
    results = Result.objects.all(race=race)
    for r in results:
        scaled_position = (race.num_competitors - (r.position-1))/race.num_competitors
        r.dividend = race.min_dividend + (race.max_dividend - race.min_dividend) * pow(scaled_position, 2)
        r.save()



# This may not be needed any more- just compute on the fly """"
# class ShareSnapshot(models.Model):
#     """ To store who owns what shares at some point in time, so we can then compute dividends """
#     athlete = models.ForeignKey(Athlete, related_name="%(app_label)s_%(class)s_athlete", on_delete=models.CASCADE)
#     volume = models.FloatField()
#     owner = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owner", on_delete=models.CASCADE)
#     timestamp = models.DateTimeField(auto_now_add=True)
#     event = models.ForeignKey(Event, on_delete=models.CASCADE, blank=True, null=True) # can be null

#     def serialize(self):
#         return {"athlete": self.athlete.serialize(),
#         "owner": self.owner.serialize(),
#         "event": self.event.serialize(),
#         "volume": self.volume,
#         "timestamp": self.timestamp}


# def make_share_snapshots(event=None):
#     owned_shares = Share.objects.all().filter(is_virtual=False)
#     for s in owned_shares:
#         snapshot = ShareSnapshot(athlete=s.athlete, volume=s.volume, owner=s.owner, event=event)
#         snapshot.save()

# def distribute_dividends(event):
#     undistributed = Result.objects.all().filter(dividend_distributed=False)
#     for d in undistributed:
#         # Check event is in the past
#         if d.event.date > datetime.now(pytz.utc):
#             print("Event is in the future, do not distribute dividends: {}".format(d.event))
#             continue
    
#         # Get share snapshots for this event and athlete
#         shares = ShareSnapshot.objects.all().filter(athlete=d.athlete,event=d.event)

#         total_share_vol = np.sum([s.volume for s in shares])

#         # Distribute cash to share owners
#         for s in shares:
#             dividend_fraction = np.round(d.ammount * s.volume/total_share_vol, 2)
#             s.owner.capital = s.owner.capital + dividend_fraction
#             s.owner.save()

#             print("Paid dividend of {} to {} for {} shares in {} at {}".format(dividend_fraction, s.owner, s.volume, s.athlete, event))

#         d.dividend_distributed = True
#         d.save()