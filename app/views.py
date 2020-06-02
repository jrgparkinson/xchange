from django.http import HttpResponse, JsonResponse
from django.http import Http404
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login
from app.forms import *
from app.models import *
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import re
import json
from django.core.serializers.json import DjangoJSONEncoder
import time
from datetime import datetime
import logging
import traceback

# Get an instance of a logger
logger = logging.getLogger(__name__)

def handler404(request, exception):
    return render(request, "app/404.html", status=404)


def handler403(request, exception):
    return render(request, "app/403.html", status=403)


def handler500(request):
    return render(request, "app/500.html", status=500)


def index(request):
    # return HttpResponse("Hello, world. You're at the polls index.")
    investors = Investor.objects.all()
    investors = sorted(investors, key=lambda i: i.total_value, reverse=True)
    investors_leaderboard = []
    pos = 1
    for i in investors:
        # inv = i.serialize()
        # inv["position"] = pos
        i.position = pos

        # portfolio = i.get_portfolio_values(season=get_current_season())
        # i.current_cash = portfolio["cash"]
        # i.current_shares = portfolio["shares"]
        # i.current_total = portfolio["combined"]

        investors_leaderboard.append(i)
        pos = pos + 1

    athletes = Athlete.objects.all()
    athletes = sorted(athletes, key=lambda a: a.get_value(), reverse=True)
    if len(athletes) > 3:
        top_athletes = athletes[:3]
    else:
        top_athletes = athletes

    for i in range(len(athletes)):
        a = athletes[i]
        a.position = i + 1
        athletes[i] = a

    # Stats
    ind = ShareIndexValue.get_value(ShareIndexValue.TOP10)
    # logger.info("{}, {}".format(ind.value, ind.daily_change))
    stats = {"top10": ShareIndexValue.get_value(ShareIndexValue.TOP10)}

    context = {
        "season": get_current_season(),
        "leaderboard": investors_leaderboard,
        "stats": stats,
        "top_athletes": top_athletes,
        "athletes": athletes,
    }
    return render(request, "app/index.html", context)


def about(request):
    context = {}
    return render(request, "app/about.html", context)

@login_required(login_url="/login/")
def auction(request):

    if request.method == "POST":

        # build list of lot details
        lot_bids_form = {}

        for field in list(dict(request.POST).keys()):

            # logger.info(field)
            m = re.match(r"^lot_(\d+)_([a-zA-Z]+)$", field)
            if m:
                
                lot_id = int(m.groups()[0])
                value = request.POST[field]

                # validate value
                if not re.match(r"[0-9\.]+", value):
                    value = 0.0
                    # logger.info("Invalid value: {}".format(value))
                    # continue

                if lot_id not in list(lot_bids_form.keys()):
                    lot_bids_form[lot_id] = {"volume": 0.0, "price": 0.0}

                price_volume= str(m.groups()[1])
                lot_bids_form[lot_id][price_volume] = float(value)

        
        # Save:
        logger.info(lot_bids_form)
        
        for id, val in lot_bids_form.items():
            try:
                lot = Lot.objects.get(pk=id)

                # Double check we can do this
                if lot.auction.start_date > current_time() or lot.auction.end_date < current_time():
                    continue

                bid = Bid.objects.all().filter(lot=lot,bidder=request.user.investor)
                if not bid:
                    bid = Bid.objects.create(lot=lot,bidder=request.user.investor,price_per_volume=val["price"], volume=val["volume"])
                else:
                    bid = bid[0]
                    bid.price_per_volume = val["price"]
                    bid.volume = val["volume"]

                
                if bid.volume > bid.lot.volume:
                    bid.volume = bid.lot.volume

                bid.save()

            except Exception as e:
                logger.info(e)
                logger.warning(traceback.print_tb(e.__traceback__))
                continue


    # current_auction = Auction.objects.all().filter(Q(start_date__lte=current_time()) & Q(end_date__gte=current_time()))
    current_auction = Auction.objects.all().filter(is_current=True)
    lots_bid = []
    # auction = None
    if len(current_auction) > 0:
        current_auction = current_auction[0]

        if current_auction.start_date < current_time() and current_auction.end_date > current_time():
            current_auction.active = True

        lots = Lot.objects.all().filter(auction=current_auction)

        for lot in lots:
            # Check for an existing bid
            bid = Bid.objects.all().filter(lot=lot,bidder=request.user.investor)
            lot.style = ""
            if bid:
                logger.info(bid)
                lot.current_bid = bid[0]

                if lot.current_bid.status == Bid.ACCEPTED:
                    lot.style = " accepted"
                elif lot.current_bid.status == Bid.REJECTED:
                    lot.style = " rejected";

            lots_bid.append(lot)

    context = {"lots_bid": lots_bid, "auction": current_auction, "all_auctions": Auction.objects.all()}
    return render(request, "app/auction.html", context)


@login_required(login_url="/login/")
def bank(request):
    investor = request.user.investor

    transaction_history = TransactionHistory.objects.all().filter((Q(sender=investor) | Q(recipient=investor)) 
    & Q(season=get_current_season()))
    transaction_history = transaction_history.order_by('-timestamp')
    transactions = []
    for t in transaction_history:
        t.description = t.description(investor)
        t.cash_in = t.cash_in(investor)
        t.cash_out = t.cash_out(investor)
        # t.transaction_type = t.transaction_type(investor)
        t.balance = t.balance(investor)

        transactions.append(t)

    context = {"loans": [], "shares_to_sell": [],
    "transactions": transactions}
    return render(request, "app/bank.html", context)


def races(request, race_id=None):
    events = Event.objects.all().filter(season=get_current_season())
    events_and_races = []
    for e in events:
        e.races = Race.objects.all().filter(event=e)
        events_and_races.append(e)
    context = {"events": events_and_races}
    return render(request, "app/races.html", context)


@login_required(login_url="/login/")
def profile(request):
    user = request.user
    inv = user.investor
    error = None

    if request.method == "POST":
        # create a form instance and populate it with data from the request:
        form = ProfileForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            # ...
            # redirect to a new URL:
            logger.info(form["uitheme"])
            inv.uitheme = form.cleaned_data["uitheme"]
            user.first_name = form.cleaned_data["first_name"]
            user.last_name = form.cleaned_data["last_name"]

            inv.save()
            user.save()

        else:
            error = "Invalid form"

    form = ProfileForm(
        initial={
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "uitheme": inv.uitheme,
            "error": error,
        }
    )

    return render(request, "app/profile.html", {"form": form})


@login_required(login_url="/login/")
def portfolio(request):
    return view_investor(request, request.user.investor.id)


def view_investor(request, investor_id):
    try:
        investor = Investor.objects.get(pk=investor_id)
    except Investor.DoesNotExist:
        raise Http404

    shares_total = investor.get_shares_wealth()

    current_val = investor.capital + shares_total
    shares_owned = investor.get_shares_owned()
    shares_owned = sorted(shares_owned, key=lambda share: share.volume, reverse=True)

    return render(
        request,
        "app/investor.html",
        {
            "investor": investor,
            "worth": {
                "total": current_val,
                "shares": shares_total,
                "cash": investor.capital,
            },
            "shares": shares_owned,
        },
    )


def view_athlete(request, athlete_id):
    try:
        athlete = Athlete.objects.get(pk=athlete_id)
    except Athlete.DoesNotExist:
        raise Http404

    trades = athlete.get_all_trades()

    current_value = athlete.get_value(current_time())
    logger.info("Current value = {}".format(current_value))
    value_one_day_ago = athlete.get_value(current_time() - timedelta(days=1.0))
    if value_one_day_ago == 0:
        value_change = np.nan
    else:
        value_change = 100.0 * (current_value - value_one_day_ago) / value_one_day_ago
    if np.isnan(value_change):
        value_change = "NaN"
    else:
        value_change = np.round(value_change, 2)

    logger.info(value_change)

    active_trades = Trade.objects.all().filter(Q(status=Trade.PENDING) & Q(season=get_current_season()))

    # Only show trades which can actually be accepted
    possible_active_trades = [t for t in active_trades if t.is_possible()]

    results = Result.objects.all().filter(athlete=athlete,race__event__season=get_current_season()).order_by("time")

    return render(
        request,
        "app/athlete.html",
        {
            "athlete": athlete,
            "value": {"current": np.round(current_value, 2), "change": value_change},
            "active_trades": possible_active_trades,
            "results": results,
        },
    )


def retrieve_investor_portfolio(request):
    investor_id = request.GET["id"]
    investor = Investor.objects.get(pk=investor_id)

    portfolio = investor.get_portfolio_values()

    return JsonResponse(portfolio)


def retrieve_athlete_value(request):
    athlete_id = request.GET["id"]
    athlete = Athlete.objects.get(pk=athlete_id)

    trades = athlete.get_all_trades()

    for t in trades:
        logger.info(
            "Trade price: {}, volume: {}, price/volume: {}".format(
                t.price, t.asset.share.volume, t.price / t.asset.share.volume
            )
        )

    return JsonResponse(
        {
            "athlete": athlete.serialize(),
            # "historical_values": athlete.get_historical_value(),
            "trades": [t.serialize() for t in trades],
        }
    )


def register(request):
    us = request.user

    # I have no idea why the extra us.id==None criteria is needed here
    if request.user.is_authenticated and not us.id == None:
        dashboard(request)
        # return render(request, 'dashboard.html')

    else:
        if request.method == "POST":
            form = SignUpForm(request.POST)
            if form.is_valid():
                form.save()
                username = form.cleaned_data.get("username")
                raw_password = form.cleaned_data.get("password1")
                user = authenticate(
                    username=username,
                    password=raw_password,
                    email=form.cleaned_data.get("email"),
                )
                login(request, user)
                user.save()

                return redirect("/profile/")

        else:
            form = SignUpForm()

        return render(request, "app/registration.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("/")


def temp(request):
    return JsonResponse({"error": "Not implemented yet"})


def dashboard(request):
    if request.user.is_authenticated:
        investor = request.user.investor

        shares = Share.objects.filter(owner=investor, season=get_current_season())
        loans = Loan.objects.filter(recipient=investor, season=get_current_season())

        # collated_shares = investor.get_shares()
        return render(request, "app/dashboard.html", {"shares": shares, "loans": loans})
    else:
        return render(request, "app/index.html")


@login_required(login_url='/login/')
def marketplace(request):
    if request.user.is_authenticated:
        return render(request, "app/marketplace.html")
    else:
        return render(request, "app/index.html")


# @login_required(login_url='/login/')
def retrieve_trades(request):

    response = {}
    try:

        if request.user.is_active:
            current_investor = request.user.investor
        else:
            current_investor = None

        if "investor_id" in request.GET:
            investor = Investor.objects.get(pk=request.GET["investor_id"])
        else:
            investor = current_investor

        if "athlete_id" in request.GET:
            logger.info("Retrieve trades for athlete id {}".format(request.GET["athlete_id"]))
            athlete = Athlete.objects.get(pk=request.GET["athlete_id"])
            if "historical" in request.GET:
                all_trades = Trade.objects.all().filter(
                    Q(asset__share__athlete=athlete) & ~Q(status=Trade.PENDING) & Q(season=get_current_season())
                )
            else:
                all_trades = Trade.objects.all().filter(
                    Q(asset__share__athlete=athlete) & Q(status=Trade.PENDING) & Q(season=get_current_season())
                )

            all_trades = [t for t in all_trades if t.is_possible()]
            # all_trades = [t for t in all_trades if t.asset.is_share() and t.asset.share.athlete==athlete]
        elif "historical" in request.GET:
            logger.info("Retrieve historical trades ")
            all_trades = Trade.objects.all().filter(
                (Q(buyer=investor) | Q(seller=investor)) & ~Q(status=Trade.PENDING) & Q(season=get_current_season())
            )
        elif "asset" in request.GET:
            asset = request.GET["asset"]
            logger.info("Retrieve trades for asset {}".format(asset))
            all_trades = Trade.objects.all().filter(
                Q(status=Trade.PENDING) & (Q(seller=None) | Q(buyer=None)) & Q(season=get_current_season())
            )

            # Get open trades only - either no seller or no buyer
            # all_trades = [t for t in all_trades if (t.seller is None) or (t.buyer is None)]
            print("Retrieved {} trades".format(len(all_trades)))

            if asset == "share":
                all_trades = [
                    t
                    for t in all_trades
                    if t.asset.is_share() and t.asset.share.volume > 0
                ]

                # only retrieve shares where they can be actioned sensibly
                all_trades = [t for t in all_trades if t.is_possible()]
            elif asset == "option":
                all_trades = [t for t in all_trades if t.asset.is_option()]
            elif asset == "future":
                all_trades = [t for t in all_trades if t.asset.is_future()]
            elif asset == "swap":
                all_trades = [t for t in all_trades if t.asset.is_swap()]

            print("Retrieved {} trades after filtering by asset: {}".format(len(all_trades), asset))

        else:
            logger.info("Retrieve standard trades")
            logger.info(request.GET)
            all_trades = Trade.objects.all().filter(
                (Q(buyer=investor) | Q(seller=investor)) & Q(status=Trade.PENDING) & Q(season=get_current_season())
            )

        # now sort
        # logger.info("Sort")
        # if "asset" in request.GET:
        if isinstance(all_trades, list):
            all_trades = sorted(all_trades, key=lambda t: t.updated, reverse=True)
        else:
            all_trades = all_trades.order_by("-updated")

        # remove trades with a strike date in the past
        all_trades = [t for t in all_trades if not (t.asset.is_future() and t.asset.contract.future.action_date < current_time())]
        # all_trades = [t for t in all_trades if not (t.asset.is_option() and t.asset.option.action_date < current_time())]

        trades = []

        # trades = [t.serialize() for t in all_trades]
        for t in all_trades:

            # logger.info(t)
            trade = t.serialize()

            if t.seller == investor:
                trade["type"] = "Sell"
            else:
                trade["type"] = "Buy"

            trade["can_accept"] = False

            # Can accept it if:
            # a) we didn't make it
            # and b) there's a seller and a buyer (direct trade) or no buyer (open trade) but we can become the buyer
            # if not t.creator == current_investor and ( (t.buyer and t.seller) or not t.seller == investor) and (t.buyer == current_investor or t.seller == current_investor):
            if current_investor and not t.creator == current_investor:

                # Options here: we can sell, or we can buy
                # We can sell if: there is a buyer
                if t.buyer and (t.seller is None or t.seller == current_investor):

                    # if this is a shares trade, also need to ensure we have the shares to sell
                    # if trade.asset.is_share() and current_investor.saleable_shares_in_athlete(trade.asset.share.athlete).volume > trade.asset.share.volume:
                    trade["can_accept"] = True

                    # For other types of trade, not sure what the criteria is

                # WE can buy if: there is a seller, and we have enough cash!
                if (
                    t.seller
                    and (t.buyer is None or t.buyer == current_investor)
                    and current_investor.capital > t.price
                ):
                    trade["can_accept"] = True

            trade["can_close"] = False
            if current_investor and (
                t.creator == current_investor or t.seller == current_investor
            ):
                trade["can_close"] = t.buyer == investor or t.seller == investor

            trades.append(trade)

        # logger.info("Trades: " +str(trades))
        if "athlete_id" in request.GET:
            trades = sorted(trades, key=lambda t: t["price"] / t["asset"]["volume"])

        response = {"trades": trades}

        if investor:
            response["investor"] = investor.serialize()
        else:
            response["investor"] = None

        if current_investor is not None:
            response["current_investor"] = current_investor.serialize()
        else:
            response["current_investor"] = None

    except Exception as e:
        logger.info("Caught: " + str(e))
        logger.info(traceback.print_tb(e.__traceback__))
        return JsonResponse({"error": str(e)})

    # logger.info("Execution time: {} seconds".format(time.time() - init_time))
    # logger.info("Serialize time: {} seconds".format(serialize_time))

    return JsonResponse(response, safe=False)


@login_required(login_url="/login/")
def action_trade(request):
    investor = request.user.investor

    logger.info(request.GET)

    trade_id = request.GET["id"]
    change = request.GET["change"]

    error = ""

    try:
        trade = Trade.objects.get(pk=trade_id)

        logger.info("Trade to modify: {}".format(trade))

        if change == "accept":
            if not trade.seller and trade.buyer != investor:
                trade.seller = investor
            if not trade.buyer and trade.seller != investor:
                trade.buyer = investor

            trade.accept_trade(action_by=investor)
        elif investor == trade.creator:
            trade.cancel_trade()
        else:
            trade.reject_trade()

    except XChangeException as e:
        return JsonResponse(make_error(e))
        # error = {"title": e.title, "description": e.desc}
    except Trade.DoesNotExist:
        error = {
            "title": "Trade no longer exists",
            "desc": "This really shouldn't have happened",
        }
    except Exception as e:
        
        traceback.print_tb(e.__traceback__)
        error = {"title": "Internal error", "desc": "The gory details: <br>" + str(e)}

    return JsonResponse({"error": error})


def get_portfolio_value(request):
    if request.user.is_authenticated:
        investor = request.user.investor

        return JsonResponse(
            {"capital": investor.capital, "shares": investor.share_value}
        )

    return JsonResponse({})


@login_required(login_url="/login/")
def create_trade(request):
    investor = request.user.investor

    logger.info(request.GET)

    # TODO: validation

    try:

        commodity = request.GET["commodityEntry"]
        tradeWith = request.GET["tradeWith"]
        price = float(request.GET["price"])
        is_sell = request.GET["buysell"] == "sell"
        if "data-asset" not in request.GET:
            logger.info("data-asset not in request.GET")
            raise InvalidAsset(desc="{} is not a valid asset".format(commodity))

        asset_type = request.GET["data-asset"]

        seller = None
        buyer = None
        other = None

        if not tradeWith == "Open":
            other = Investor.objects.get(user__username=tradeWith)

        if is_sell:
            seller = investor
            buyer = other
        else:
            buyer = investor
            seller = other

        # share_match = re.match(r"([\w ]+)/([\.\d]+)", commodity)
        if asset_type == 'share':
            ath_id = request.GET["data-athlete"] # share_match.group(1)
            volume = float(request.GET["data-volume"]) # float(share_match.group(2))
            athlete = Athlete.objects.get(id=int(ath_id))

            trade = Trade.make_share_trade(
                athlete, volume, investor, price, seller, buyer
            )

        elif asset_type == "future" or asset_type == "option":
            ath_id = request.GET["data-athlete"] 
            volume = float(request.GET["data-volume"]) 
            strike_price = float(request.GET["data-strike-price"]) 
            owner_obligation = request.GET["data-future-buy-sell"]
            athlete = Athlete.objects.get(id=int(ath_id))
            strike_date =  datetime.strptime(request.GET["data-date"], "%Y-%m-%dT%H:%M:%S.%fZ")

            # owner_obligation
            # if is_sell:
            #     owner = other
            #     seller = investor

            # logger.info(strike_date)
            
            if asset_type == "option":
                # holder = request.GET["data-holder"]
                # trade = Trade.make_option_trade(athlete, volume, investor, price, seller, buyer, strike_date, strike_price, holder)
                raise InvalidAsset(desc="Options not supported yet, sorry".format(commodity))
            else:
                
                trade = Trade.make_future_trade(athlete, volume, investor, price, seller, buyer, 
                strike_date, strike_price, owner_obligation)
            
        else:
            logger.info("Invalid asset type: {}".format(asset_type))
            raise InvalidAsset(desc="{} is not a valid asset".format(commodity))

    except Athlete.DoesNotExist:
        raise AthleteDoesNotExist(desc="{} does not exist".format(ath))
    except XChangeException as e:
        return JsonResponse(make_error(e))
    
    except Exception as e:
        logger.warning(traceback.print_tb(e.__traceback__))
        return JsonResponse(make_error(e))

    return JsonResponse({})


def asset_price(request):

    try:
        logger.info(request.GET)
        if request.GET["data-asset"] in ['share', 'future', 'option']:
            athlete = Athlete.objects.get(pk=int(request.GET["data-athlete"]))
            value = athlete.get_value()

            total_val = float(request.GET["data-volume"]) * value

            return JsonResponse({"value": "{}: {} per share".format(athlete.name, value)})
        else:
            return JsonResponse({"value": "Unknown"})
    except Exception as e:
        logger.info(e)
        logger.warning(traceback.print_tb(e.__traceback__))
        return JsonResponse({"value": "Unknown"})


def make_error(e):
    logger.info("Caught error " + str(e))
    if isinstance(e, XChangeException):
        return {"error": {"title": e.title, "desc": e.desc}}
    else:
        return {
            "error": {
                "title": "Internal error",
                "desc": "An internal error has occured",
            }
        }


def get_investors(request):
    inv = Investor.objects.all()
    if "ignore_self" in request.GET and request.GET["ignore_self"]:
        inv = [i for i in inv if not i == request.user.investor]

    investors = [i.serialize() for i in inv]
    return JsonResponse({"investors": investors})


def get_athletes(request):
    if request.user.is_authenticated:
        investor = request.user.investor
    else:
        investor = None

    athletes = [i.serialize(investor) for i in Athlete.objects.all()]
    return JsonResponse({"athletes": athletes})


def get_race(request):
    try:
        race_id = request.GET["id"]

        race = Race.objects.get(pk=race_id)

        results = Result.objects.all().filter(race=race)
        results_arr = [r.serialize() for r in results]

        return JsonResponse({"race": race.serialize(), "results": results_arr})

    except XChangeException as e:
        error = {"title": e.title, "description": e.desc}
    except Race.DoesNotExist:
        error = "Race does not exist"

    return JsonResponse({"error": error})


def get_event(request):
    try:
        event_id = request.GET["id"]

        event = Event.objects.get(pk=event_id)
        return JsonResponse({"event": event.serialize()})

    except XChangeException as e:
        error = {"title": e.title, "description": e.desc}
    except Event.DoesNotExist:
        error = "Event does not exist"

    return JsonResponse({"error": error})


def trades(request):
    if request.user.is_authenticated:
        investor = request.user.investor
        
        return render(
            request,
            "app/trades.html",
            {"trades": Trade.objects.filter( (Q(seller=investor) | Q(buyer=investor)) & Q(season=get_current_season()))},
        )
    else:
        return render(request, "app/index.html")

@login_required(login_url='/login/')
def notifications_exist(request):
    n = Notification.objects.all().filter(Q(investor=request.user.investor) & Q(status=Notification.UNSEEN))
    return JsonResponse({"num_notifications": len(n)})

@login_required(login_url='/login/')
def get_notifications(request):
    # Get all non-dismissed for displaying
    notifications = Notification.objects.all().filter(Q(investor=request.user.investor) & ~Q(status=Notification.DISMISSED)).order_by('-datetime')
    nots = [n.serialize() for n in notifications]
    return JsonResponse({"notifications": nots})

@login_required(login_url='/login/')
def set_notification_status(request):
    logger.info(request.GET)

    if 'all_seen' in request.GET and request.GET['all_seen']:
        notifications = Notification.objects.all().filter(Q(investor=request.user.investor)& Q(status=Notification.UNSEEN))
        for n in notifications:
            n.status = Notification.SEEN
            n.save()

    if 'dismissed' in request.GET:
        try:
            notif = Notification.objects.get(id=request.GET['dismissed'])
            notif.status = Notification.DISMISSED
            notif.save()

        except Notification.DoesNotExist:
            print("Notification does not exist")
            return JsonResponse({"error": "Notification does not exist"})

    if 'seen' in request.GET:
        try:
            notif = Notification.objects.get(id=request.GET['seen'])
            notif.status = Notification.SEEN
            notif.save()

        except Notification.DoesNotExist:
            print("Notification does not exist")
            return JsonResponse({"error": "Notification does not exist"})
            

    return JsonResponse({})
