from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta, datetime
import pytz
import numpy as np
from app.errors import * 

def current_time():
    return datetime.now(pytz.utc)

def format_currency(currency):
    locale.setlocale( locale.LC_ALL, '' )
    currency_str = locale.currency( currency, grouping=True ) + "M"
    return currency_str

class Entity(models.Model):
    capital = models.FloatField(default=1000)

    def serialize(self):
        if self.is_bank():
            return self.bank.serialize()
        elif self.is_investor():
            return self.investor.serialize()
        else:
            return {"capital": self.capital}

    def can_sell_commodity(self, commodity):
        if commodity.is_share():
            owned_shares = self.shares_in_athlete(commodity.share.athlete)
            if owned_shares and owned_shares.volume >= commodity.share.volume:
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
        return {"name": self.user.username,
            "capital": self.capital}

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Investor.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.investor.save()

class Athlete(models.Model):
    """
    An athlete who earns dividends for their share holders
    """
    name = models.CharField(max_length=100, unique=True)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name

    def serialize(self):
        return {"name": self.name}

    def get_total_volume_of_shares(self):
        shares = Share.objects.filter(athlete=self)
        volume = np.sum(np.array([float(s.volume) for s in shares]))
        return volume

class Commodity(models.Model):
    """
    Something that can be bought and sold
    A virtual commodity is one involved in an open trade
    
    The owner can be null if it is a virtual commodity
    
    """
    
    owner = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owner", on_delete=models.CASCADE, blank=True, null=True)
    is_virtual = models.BooleanField(default=False) # need ability to create virtual commodities for an open buy trade
 

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
            val = "Commodity owned by {}".format(self.owner)
            if self.is_virtual:
                val = val + " (virtual)"
            return val

class Share(Commodity):
    """
    Most common type of commodity - a share in an athlete
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
            return {"owner": self.owner,
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
            new_share = Share(athlete=self.athlete, volume=vol, owner=self.owner)
            new_share.save()
            return new_share


    
class Future(Commodity):
    """ An agreement to buy/sell in the future at a fixed price """

    strike_price = models.FloatField()
    action_date = models.DateTimeField()

class Option(Future):
    """ An option is a future where one party has the option to go through with the trade or not """

    # Note that banks cannot hold options, only investors
    # option_holder = models.ForeignKey(Investor, related_name="%(app_label)s_%(class)s_option_holder", on_delete=models.CASCADE)
    # option holder is just the owner
    current_option = models.BooleanField(default=True)  # whether to conduct trade, can be change by the option holder

class Swap(Commodity):
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
    Transfer of a commodity between two entities.
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

    commodity = models.ForeignKey(Commodity, related_name="%(app_label)s_%(class)s_commodity", on_delete=models.CASCADE)

    seller = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_seller", on_delete=models.CASCADE, blank=True, null=True)
    buyer = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_buyer", on_delete=models.CASCADE, blank=True, null=True)

    # Who initiated the trade (offered to sell/asked to buy)?
    creator = models.ForeignKey(Investor, related_name="%(app_label)s_%(class)s_creator", on_delete=models.CASCADE)

    price = models.FloatField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    decision_dt = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=PENDING)

    def __str__(self):
        return "{} from {} to {} for {} ({})".format(self.commodity, self.seller, self.buyer, self.price, self.status)

    def serialize(self):
        json = {"id": self.pk,
        "commodity": self.commodity.serialize(),
        "creator": self.creator.serialize(),
        "price": self.price,
        "created": self.created,
        "updated": self.updated,
        "status": self.status,
        "decision_dt": self.decision_dt}

        if self.buyer:
            json["buyer"] = self.buyer.serialize()
        if self.seller:
            json["seller"] = self.seller.serialize()

        return json

    def make_share_trade(athlete, volume, creator, price, seller=None, buyer=None):
        virtual_share = Share(athlete=athlete, volume=volume, is_virtual=True)
        virtual_share.save()

        trade = Trade.make_trade(virtual_share, creator, price, seller, buyer)

    def make_trade(commodity, creator, price, seller=None, buyer=None):
        price = np.round(price, 2) # ensure price is always to 2 DP
        trade = Trade(commodity=commodity, seller=seller, buyer=buyer, creator=creator, price=price, status=Trade.PENDING)
        trade.save()
        return trade

    def reject_trade(self):
        if not self.status == self.PENDING:
            raise TradeNotPending

        self.status=self.REJECTED
        self.save()

    def cancel_trade(self):
        if not self.status == self.PENDING:
            raise TradeNotPending

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

        # Check seller has commodity to sell
        if self.commodity.is_share():
            if not self.seller.can_sell_commodity(self.commodity):
                raise InsufficientShares

            # Do the trade
            print("Accepted trade: {}".format(self)) #  for {} from {} to {}".format(self.commodity, self.seller, self.buyer))
            # print(" Before, seller ({}) owns: {}".format(self.seller, self.seller.shares_in_athlete(self.commodity.share.athlete)))
            # print(" Before, buyer ({}) owns: {}".format(self.buyer, self.buyer.shares_in_athlete(self.commodity.share.athlete)))
            share = self.seller.get_share(self.commodity.share)
            share.transfer(to=self.buyer, vol=self.commodity.share.volume)
            self.status = self.ACCEPTED
            self.save()

            # Transfer cash if all successful (have already confirmed the cash is available to transfer)
            # self.seller.capital = self.seller.capital + self.price
            # self.buyer.capital = self.buyer.capital - self.price
            b = self.buyer
            b.transfer_cash_to(ammount=self.price, to=self.seller, reason=str(self))

            self.seller.save()
            self.buyer.save()

            # print(" After, seller ({}) owns: {}".format(self.seller, self.seller.shares_in_athlete(self.commodity.share.athlete)))
            # print(" After, buyer ({}) owns: {}".format(self.buyer, self.buyer.shares_in_athlete(self.commodity.share.athlete)))

            

        else:
            print("Unable to complete trade for {}".format(self.commodity))
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
        # lender.capital = lender.capital - balance
        # recipient.capital = recipient.capital + balance
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
            # self.recipient.capital = self.recipient.capital - interest_ammount
            # self.lender.capital = self.lender.capital + interest_ammount

            self.recipient.transfer_cash_to(interest_ammount, self.lender, reason=str(self))

        else:
            ammount_payable = self.recipient.capital

            self.lender.capital = self.lender.capital + ammount_payable
            self.recipient.capital = 0

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

    def serialize(self):
        return {"sender": self.sender.serialize(),
        "recipient": self.recipient.serialize(),
        "ammount": self.ammount,
        "reason": self.reason}

class Event(models.Model):
    """ Athletes compete in Events and hence earn dividends """
    name = models.CharField(max_length=100)
    date = models.DateTimeField()

    def __str__(self):
        return "{} ({})".format(self.name, self.date.strftime("%d/%m/%Y"))

    def serialize(self):
        return {"name": self.name,
        "date": self.date}

class Dividend(models.Model):
    """ Dividends are recorded for athletes when they
    perform well in an event.

    They are entered manually by the XChange administrator, and automatically distributed 
    in a proportional manner to those
    who owned shares in the athlete at the start of the event. 
    """
    athlete = models.ForeignKey(Athlete, related_name="%(app_label)s_%(class)s_athlete", on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    ammount = models.FloatField()
    has_been_distributed = models.BooleanField(default=False)

    def serialize(self):
        return {"athlete": self.athlete.serialize(),
        "event": self.event.serialize(),
        "ammount": self.ammount,
        "has_been_distributed": self.has_been_distributed}

class ShareSnapshot(models.Model):
    """ To store who owns what shares at some point in time, so we can then compute dividends """
    athlete = models.ForeignKey(Athlete, related_name="%(app_label)s_%(class)s_athlete", on_delete=models.CASCADE)
    volume = models.FloatField()
    owner = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owner", on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, blank=True, null=True) # can be null

    def serialize(self):
        return {"athlete": self.athlete.serialize(),
        "owner": self.owner.serialize(),
        "event": self.event.serialize(),
        "volume": self.volume,
        "timestamp": self.timestamp}


def make_share_snapshots(event=None):
    owned_shares = Share.objects.all().filter(is_virtual=False)
    for s in owned_shares:
        snapshot = ShareSnapshot(athlete=s.athlete, volume=s.volume, owner=s.owner, event=event)
        snapshot.save()

def distribute_dividends(event):
    undistributed = Dividend.objects.all().filter(has_been_distributed=False)
    for d in undistributed:
        # Check event is in the past
        if d.event.date > datetime.now(pytz.utc):
            print("Event is in the future, do not distribute dividends: {}".format(d.event))
            continue
    
        # Get share snapshots for this event and athlete
        shares = ShareSnapshot.objects.all().filter(athlete=d.athlete,event=d.event)

        total_share_vol = np.sum([s.volume for s in shares])

        # Distribute cash to share owners
        for s in shares:
            dividend_fraction = np.round(d.ammount * s.volume/total_share_vol, 2)
            s.owner.capital = s.owner.capital + dividend_fraction
            s.owner.save()

            print("Paid dividend of {} to {} for {} shares in {} at {}".format(dividend_fraction, s.owner, s.volume, s.athlete, event))

        d.has_been_distributed = True
        d.save()