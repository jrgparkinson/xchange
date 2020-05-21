from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta
import pytz
import numpy as np
from app.errors import * 

def format_currency(currency):
    locale.setlocale( locale.LC_ALL, '' )
    currency_str = locale.currency( currency, grouping=True ) + "M"
    return currency_str

class Entity(models.Model):
    capital = models.FloatField(default=25000000)

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
            return share
        except Share.DoesNotExist:
            return None

        except Share.MultipleObjectsReturned:
            print(Share.objects.filter(owner=self, is_virtual=False, athlete=athlete))

    def get_share(self, share):
        try:
            share = Share.objects.get(owner=self, is_virtual=False, athlete=share.athlete)
            return share
        except Share.DoesNotExist:
            return None

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

class Investor(Entity):
    """
    An investor is an individual who trades stuff
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    

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
 
    def is_share(self):
        try:
            share = self.share
        except Share.DoesNotExist:
            return False
        return True

class Share(Commodity):
    """
    Most common type of commodity - a share in an athlete
    """

    athlete = models.ForeignKey(Athlete, related_name="%(app_label)s_%(class)s_athlete", on_delete=models.CASCADE)
    volume = models.FloatField()

    def __repr__(self):
        return "{}: {}".format(self.athlete, self.volume)

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

    def make_trade(commodity, creator, price, seller=None, buyer=None):
        if commodity.is_share():
            tradeable_commodity = Share(athlete=commodity.share.athlete, volume=commodity.share.volume, is_virtual=True)
            tradeable_commodity.save()
        else:
            tradeable_commodity = commodity

        trade = Trade(commodity=tradeable_commodity, seller=seller, buyer=buyer, creator=creator, price=price, status=Trade.PENDING)
        return trade

    def accept_trade(self, action_by):
        if not self.buyer or not self.seller:
            raise NoBuyerOrSeller
        
        # Check action_by can do this
        if not self.seller == None and not action_by == self.seller:
            print("Trade seller = {}".format(self.seller))
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
            share = self.seller.get_share(self.commodity.share)
            share.transfer(to=self.buyer, vol=self.commodity.share.volume)
            self.status = self.ACCEPTED
            self.save()

            print("Accepted trade for {} from {} to {}".format(self.commodity, self.seller, self.buyer))

        else:
            print("Unable to complete trade for {}".format(self.commodity))
            pass



class Loan(models.Model):
    """ One entity may loan another entity some capital, which is repayed at some interest rate
    """
    lender = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_lender", on_delete=models.CASCADE, blank=False, null=False)
    recipient = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_recipient", on_delete=models.CASCADE, blank=False, null=False)

    created = models.DateTimeField(auto_now_add=True)

    # Interest rate in %/week
    interest_rate = models.FloatField()

    # How much needs to be repayed
    balance = models.FloatField()

    # Default interval is weekly
    repayment_interval = models.DurationField(default=timedelta(days=7))


class Debt(models.Model):
    """ Having introduced loans, we must now allow for debt 
    E.g. if someone is unable to pay back a loan
    """
    owed_by = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owed_by", on_delete=models.CASCADE, blank=False, null=False)
    owed_to = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_owed_to", on_delete=models.CASCADE, blank=False, null=False)

    created = models.DateTimeField(auto_now_add=True)

    ammount = models.FloatField()

class TransactionHistory(models.Model):
    """ We should keep a track of all transactions made """
    sender = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_from", on_delete=models.CASCADE, blank=False, null=False)
    recipient = models.ForeignKey(Entity, related_name="%(app_label)s_%(class)s_to", on_delete=models.CASCADE, blank=False, null=False)
    ammount = models.FloatField()
    reason = models.TextField() # e.g. buying volume of shares from X, repaying loan to X



class Event(models.Model):
    """ Athletes compete in Events and hence earn dividends """
    name = models.CharField(max_length=100)
    date = models.DateTimeField()


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