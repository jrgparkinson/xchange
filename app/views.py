from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login
from app.forms import SignUpForm
from app.models import *
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import re
import json
from django.core.serializers.json import DjangoJSONEncoder

def index(request):
    # return HttpResponse("Hello, world. You're at the polls index.")
    context = {}
    return render(request, "app/index.html", context)

def about(request):
    context = {}
    return render(request, "app/about.html", context)


def profile(request):
    if request.user.is_authenticated:
        return render(request, 'app/profile.html')
    else:
        return render(request, 'app/index.html')

@login_required(login_url='/login/')
def portfolio(request):
    return view_investor(request, request.user.investor.id)

def view_investor(request, investor_id):
    try:
        investor = Investor.objects.get(pk=investor_id)
    except Investor.DoesNotExist:
        raise Http404

    shares_total = investor.get_shares_wealth()

    current_val = investor.capital + shares_total

    return render(request, 'app/investor.html', {
        "investor": investor,
        "worth": {"total": current_val,
        "shares": shares_total,
        "cash": investor.capital},
        "shares": investor.get_shares_owned()})

def view_athlete(request, athlete_id):
    try:
        athlete = Athlete.objects.get(pk=athlete_id)
    except Athlete.DoesNotExist:
        raise Http404

    trades = athlete.get_all_trades()

    current_value = athlete.get_value(current_time())
    print("Current value = {}".format(current_value))
    value_one_day_ago = athlete.get_value(current_time()-timedelta(days=1))
    value_change = 100.0*(current_value - value_one_day_ago)/current_value
    if np.isnan(value_change):
        value_change = "NaN"
    else:
        value_change = np.round(value_change, 2)

    print(value_change)

    active_trades = Trade.objects.all().filter(Q(status=Trade.PENDING))

    return render(request, 'app/athlete.html', {"athlete": athlete, 
    "value": {"current": np.round(current_value, 2),
    "change": value_change},
    "active_trades": active_trades
    })

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
        print("Trade price: {}, volume: {}, price/volume: {}".format(t.price, t.asset.share.volume, t.price/t.asset.share.volume))

    return JsonResponse({"athlete": athlete.serialize(), 
    # "historical_values": athlete.get_historical_value(),
    "trades": [t.serialize() for t in trades]})

def register(request):
    us = request.user

    # I have no idea why the extra us.id==None criteria is needed here
    if request.user.is_authenticated and not us.id == None:
        dashboard(request)
        #return render(request, 'dashboard.html')

    else:
        if request.method == 'POST':
            form = SignUpForm(request.POST)
            if form.is_valid():
                form.save()
                username = form.cleaned_data.get('username')
                raw_password = form.cleaned_data.get('password1')
                user = authenticate(username=username, password=raw_password, 
                email=form.cleaned_data.get('email'))
                login(request, user)
                user.save()
                
                return redirect('/profile/')
                
                
        else:
            form = SignUpForm()

        return render(request, 'app/registration.html', {'form' : form})


def logout_view(request):
    logout(request)
    return redirect('/')


def temp(request):
    return JsonResponse({"error": "Not implemented yet"})




def dashboard(request):
    if request.user.is_authenticated:
        investor = request.user.investor

        shares = Share.objects.filter(owner=investor)
        loans = Loan.objects.filter(recipient=investor)

        # collated_shares = investor.get_shares()
        return render(request, 'app/dashboard.html', {'shares': shares, 'loans': loans})
    else:
        return render(request, 'app/index.html')


def marketplace(request):
    if request.user.is_authenticated:
        #shares = Share.objects.filter(owner=request.user.investor)

        # Remove testing:
        #investor = request.user.investor
        #open_trade = OpenTrade.objects.filter(buyer=investor).first()
        #investor.can_fulfil_trade(open_trade)

        return render(request, 'app/marketplace.html')
    else:
        return render(request, 'app/index.html')



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
            athlete = Athlete.objects.get(pk=request.GET["athlete_id"])
            if "historical" in request.GET:
                all_trades = Trade.objects.all().filter(Q(asset__share__athlete=athlete)  & ~Q(status=Trade.PENDING))
            else:
                all_trades = Trade.objects.all().filter(Q(asset__share__athlete=athlete) & Q(status=Trade.PENDING)) 
            # all_trades = [t for t in all_trades if t.asset.is_share() and t.asset.share.athlete==athlete]
        elif "historical" in request.GET:
            all_trades = Trade.objects.all().filter((Q(buyer=investor) | Q(seller=investor)) & ~Q(status=Trade.PENDING))
        else:
            all_trades = Trade.objects.all().filter((Q(buyer=investor) | Q(seller=investor)) & Q(status=Trade.PENDING))

        all_trades = all_trades.order_by('-updated')

        trades = []
        for t in all_trades:
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
            if current_investor and not t.creator==current_investor:

                # Options here: we can sell, or we can buy
                # We can sell if: there is a buyer
                if t.buyer and (t.seller is None or t.seller == current_investor):

                    # if this is a shares trade, also need to ensure we have the shares to sell
                    # if trade.asset.is_share() and current_investor.saleable_shares_in_athlete(trade.asset.share.athlete).volume > trade.asset.share.volume:
                    trade["can_accept"] = True

                    # For other types of trade, not sure what the criteria is

                # WE can buy if: there is a seller, and we have enough cash!
                if t.seller and (t.buyer is None or t.buyer==current_investor) and current_investor.capital > t.price:
                    trade["can_accept"] = True


            trade["can_close"] = False
            if current_investor and (t.creator == current_investor or t.seller==current_investor):
                trade["can_close"] = (t.buyer == investor or t.seller==investor)



            trades.append(trade)


        # print("Trades: " +str(trades))
        if "athlete_id" in request.GET:
            trades = sorted(trades, key=lambda t: t["price"]/t["asset"]["volume"])

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
        print("Caught: " + str(e))

    return JsonResponse(response, safe=False)

@login_required(login_url='/login/')
def action_trade(request):
    investor = request.user.investor

    print(request.GET)

    trade_id = request.GET["id"]
    change = request.GET["change"]
    
    error = ""

    try:
        trade = Trade.objects.get(pk=trade_id)

        print("Trade to modify: {}".format(trade))
    
        if change == "accept":
            if (not trade.seller and trade.buyer != investor):
                trade.seller = investor
            if (not trade.buyer and trade.seller != investor):
                trade.buyer = investor

            trade.accept_trade(action_by=investor)
        elif investor == trade.creator:
            trade.cancel_trade()
        else:
            trade.reject_trade()

    except XChangeException as e:
        error = {"title": e.title, "description": e.desc}
    except Trade.DoesNotExist:
        error = "Trade no longer exists"

    return JsonResponse({"error": error})

@login_required(login_url='/login/')
def create_trade(request):
    investor = request.user.investor

    print(request.GET)

    # TODO: validation

    try:

        commodity = request.GET["commodityEntry"]
        tradeWith = request.GET["tradeWith"]
        price = float(request.GET["price"])
        is_sell = request.GET["buysell"] == "sell"

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
        
        share_match = re.match(r"([\w ]+)/([\.\d]+)", commodity)
        if share_match:
            ath = share_match.group(1)
            volume = float(share_match.group(2))
            athlete = Athlete.objects.get(name=ath)

            # print(price)
           
            trade = Trade.make_share_trade(athlete, volume, investor, price, seller, buyer)

        else:
            print("Invalid commodity")
            raise InvalidCommodity(desc="{} is not a valid commodity".format(commodity))
    
    except Athlete.DoesNotExist:
        raise AthleteDoesNotExist(desc="{} does not exist".format(ath))
    except XChangeException as e:
        return JsonResponse(make_error(e))
    except Exception as e:
        return JsonResponse(make_error(e))


    return JsonResponse({})
    # trade_type = request.GET["type"]

    # if trade_type == "BUY":
    #     trades = Trade.objects.all().filter(buyer=investor)
    # else:
    #     trades = Trade.objects.all().filter(seller=investor)

    # return JsonResponse({"error": "Not implemented yet"})

def make_error(e):
    print("Caught error " + str(e))
    if isinstance(e, XChangeException):
        return {"error": {"title": e.title, "desc": e.desc}}
    else:
        return {"error": {"title": "Internal error", "desc": "An internal error has occured"}}


def get_investors(request):
    inv = Investor.objects.all()
    if "ignore_self" in request.GET and request.GET["ignore_self"]:
        inv = [i for i in inv if not i == request.user.investor]

    investors = [i.serialize() for i in inv]
    return JsonResponse({"investors": investors})

def get_athletes(request):
    athletes = [i.serialize() for i in Athlete.objects.all()]
    return JsonResponse({"athletes": athletes})

# @login_required
# def marketplace_buying(request):

#     # Get open trades where the buyer is known
#     buy_trades = OpenTrade.objects.filter(Q(status=Trade.PENDING)).order_by('-updated')

#     return render(request, 'marketplace_buy.html', {'buy_trades': buy_trades})

# @login_required
# def marketplace_selling(request):

#     # Get trades where someone wants to sell a share but there is no buyer
#     sell_trades = Trade.objects.filter(Q(buyer=None) & Q(status=Trade.PENDING)).order_by('-updated')

#     return render(request, 'marketplace_sell.html', {'sell_trades': sell_trades})



# @login_required
# def get_direct_trades(investor):
#     direct_trades = Trade.objects.filter(((Q(buyer=investor) & ~Q(seller=None)) | Q(seller=investor) & ~Q(buyer=None))  & Q(status=Trade.PENDING)).order_by('-updated')

#     return direct_trades

# @login_required
# def get_marketplace_sell_trades(investor):
#     sell_trades = Trade.objects.filter(Q(seller=investor) & Q(buyer=None) & Q(status=Trade.PENDING)).order_by('-updated')

#     return sell_trades

# @login_required
# def get_marketplace_buy_trades(investor):

#     buy_trades = OpenTrade.objects.filter(Q(buyer=investor) & Q(status=Trade.PENDING)).order_by('-updated')

#     return buy_trades

# @login_required
# def incoming_trades(request):

#     investor = request.user.investor

#     # Direct trades - i.e. both buyer and seller are defined, and this user is one of them
#     direct_trades = get_direct_trades(investor)

#     # Open trades where this is the seller
#     buy_trades = get_marketplace_buy_trades(investor)

#     sell_trades = get_marketplace_sell_trades(investor)

#     return render(request, 'incoming_trades.html', {'direct_trades': direct_trades, 'buy_trades': buy_trades, 'sell_trades': sell_trades})

 
# @login_required
# def past_trades(request):

#     investor = request.user.investor
#     past_trades = Trade.objects.filter((Q(buyer=investor) | Q(seller=investor)) & ~Q(status=Trade.PENDING) ).order_by('-updated')

#     return render(request, 'past_trades.html', {'past_trades': past_trades})

# @login_required
# def make_trade(request):

#     investor = request.user.investor

#     #shares = Share.objects.filter(owner=investor)
#     sellable_shares = investor.get_sellable_shares()

#     print(sellable_shares)

#     # Get all shares excluding those from the current investor
#     all_collated_shares = Investor.get_all_shares(investor)
    
#     other_investors = Investor.objects.filter(~Q(user = request.user))

#     return render(request, 'make_trade.html', {'sellable_shares': sellable_shares, 'other_investors': other_investors,
#         'all_collated_shares': all_collated_shares})    
 

# def get_investors_for_runner_obj(runner):
#     shares = Share.objects.filter(Q(runner=runner))

#     print('Shares for runner' + str(shares))

#     # Now get a list of investors who own these shares, and how many they own each
#     investors = []

#     for s in shares:
        
#         investor = s.owner

#         #Check if we already have this investor
#         investor_exists = False
#         for i in investors:
#             if i['investor_id'] == investor.id:
#                 investor_exists = True
#                 i['num_shares'] = i['num_shares'] + 1

#         if not investor_exists:
#             investors.append({'investor_id': investor.id, 'investor_name': str(investor), 'num_shares': 1})

#     print(investors)

#     return investors

# def get_investors_for_runner(request):
#     print('get_investors_for_runner')

#     status = 0

#     runner_id = int(request.GET['runner_id'])
#     print('Runner id: ' + str(runner_id))
    
#     runner = Runner.objects.get(pk=runner_id)

#     print('Get investors for runner: ' + str(runner))
    
#     investors =  get_investors_for_runner_obj(runner)

#     #investors = []
#     payload = {'investors': investors}

#     return HttpResponse(json.dumps(payload), content_type='application/json')


# @login_required
# def create_trade(request):

#     status = 0
#     err_msg = 'Unknown error, sorry!'

#     #'user_id': user_id, 'runner_id': runner_id, 'num_shares': num_shares, 'share_price': share_price, 'trade_width': trade_width}


#     seller_id = int(request.GET['seller_id'])
#     runner_id = int(request.GET['runner_id'])
#     num_shares = float(request.GET['num_shares'])
#     share_price = float(request.GET['share_price'])
#     buyer_id = int(request.GET['buyer_id'])

#     print('Create trade - got details')

#     # Basic form checks
#     if not int(num_shares) == num_shares:
#         status = 4
#         err_msg = 'Number of shares must be an integer'

#     num_shares = int(num_shares)

#     if share_price <= 0:
#         status = 5
#         err_msg = 'Share price must be greater than 0'

#     if not status == 0:
#         payload = {'status': status, 'err_msg': err_msg}
#         return HttpResponse(json.dumps(payload), content_type='application/json')

#     # Check trade is legit. i.e. that seller has enough shares


#         #    1) You're trying to sell more shares than you have
#         #    2) You're trying to buy more shares than someone has
#         #    3) You're trying to spend more money than you have

#     runner = Runner.objects.get(pk=runner_id)
#     creator = request.user.investor

#     if seller_id > 0:
#         print('Create trade - checking seller')

#         seller = Investor.objects.get(pk=seller_id)

#         seller_shares = Share.objects.filter(owner=seller, runner=runner)
#         if seller_shares.count() < num_shares:
#             status = 1
#             if seller == creator:
#                 err_msg = 'You do not have this many shares to sell'
#             else:
#                 err_msg = 'The seller does not have this many share to sell'

#     if buyer_id > 0:
#         print('Create trade - checking buyer')

#         buyer = Investor.objects.get(pk=buyer_id)

#         # Only care about insufficient funds if this person is proposing the trade
#         if num_shares*share_price > buyer.capital and buyer == creator:
#             status = 2
#             err_msg = 'You do not have enough capital to make this trade'

#     print('Create trade - status' + str(status))

#     if status == 0:
#         # Execute trade

#         # Direct trade
#         if buyer_id >= 0 and seller_id >= 0:
#             print('Make direct trade')
#             buyer = Investor.objects.get(pk=buyer_id)
#             seller = Investor.objects.get(pk=seller_id)

#             # Find the shares to trade
#             shares = Share.objects.filter(owner=seller, runner=runner)[:num_shares]

#             print('Got shares')

#             for s in shares:
#                 print(s)
#                 trade = Trade.objects.create(seller=seller,buyer=buyer, price=share_price, creator=creator, share=s)
#                 #trade.save()

#         # Known seller with specific shares
#         elif seller_id >= 0:
#             print('Make trade with known seller but no buyer')

#             seller = Investor.objects.get(pk=seller_id)

#             # Find the shares to trade
#             shares = Share.objects.filter(owner=seller, runner=runner)[:num_shares]

#             print('Got shares')
#             for s in shares:
#                 print(s)
#                 trade = Trade.objects.create(seller=seller, share=s, price=share_price, creator=creator)    
#                 print('Made trade')
#                 #trade.save()

#         # Known buyer but no specific share
#         elif buyer_id >= 0:
#             print('Make trade with known buyer but no seller')

#             buyer = Investor.objects.get(pk=buyer_id)

#             for i in range(0,num_shares):
#                 trade = OpenTrade.objects.create(buyer=buyer, runner=runner, price=share_price, creator=creator)
#                 #trade.save()

#         else:
#             # this should never happen - no seller or buyer
#             status = -1

#     print('Final status: ' + str(status))
#     payload = {'status': status, 'err_msg': err_msg}
#     return HttpResponse(json.dumps(payload), content_type='application/json')
    

# @login_required
# def respond_to_trade(request):

#     trade_id = int(request.GET['trade_id'])
#     response = str(request.GET['response'])

#     trade = Trade.objects.get(pk=trade_id)

#     # Check that this response is valid (i.e. both parties have sufficient capital, or it's being rejected)
#     success = (response == Trade.REJECTED or response == Trade.CANCELLED) or trade.check_if_allowed()

#     if success:
#         success = trade.set_status(response)
#         trade.save()
    
#     payload = {'trade_allowed': success}

#     return HttpResponse(json.dumps(payload), content_type='application/json')
#     #return HttpResponse()

# @login_required
# def respond_to_open_trade(request):

#     trade_id = int(request.GET['trade_id'])
#     response = str(request.GET['response'])
#     seller_id = int(request.GET['seller_id'])

#     trade = OpenTrade.objects.get(pk=trade_id)

#     success = True

#     # Check that this response is valid (i.e. both parties have sufficient capital, or it's being rejected)
#     if response == Trade.REJECTED or response == Trade.CANCELLED:
#         trade.status = response;
#         trade.save()

#     else:
#         # Need to convert this to a direct trade, then confirm that trade
#         seller = Investor.objects.get(pk=seller_id)

#         success = trade.set_status(Trade.ACCEPTED, seller, s)        
    
#     payload = {'trade_allowed': success}

#     return HttpResponse(json.dumps(payload), content_type='application/json')

def trades(request):
    if request.user.is_authenticated:
        investor = request.user.investor
        # shares = Share.objects.filter(owner=investor)

        # Remove this testing:
        #runner = Runner.objects.get(pk=2)
        #get_investors_for_runner_obj(runner)
        #trade = Trade.objects.create(seller=investor, share=shares[0], price=1.0, creator=investor)
        #incoming_trades = get_direct_trades(investor)
        #marketplace_trades = get_marketplace_buy_trades(investor)    
        #s = investor.get_sellable_shares()
#         collated_shares = investor.get_shares()
#         other_investors = Investor.objects.filter(~Q(user = request.user))
#         incoming_trades = Trade.objects.filter(Q(buyer=investor) | Q(seller=investor) & Q(status=Trade.PENDING))
#         past_trades = Trade.objects.filter(Q(buyer=investor) | Q(seller=investor)) #.filter(Q(income__gte=5000) | Q(income__isnull=True))

#         return render(request, 'trades.html', {'collated_shares': collated_shares, 'other_investors': other_investors, 
#             'shares': shares, 'past_trades': past_trades,
#             #'buy_requests': buy_requests, 'sell_requests': sell_requests
#             'incoming_trades': incoming_trades
#             })
        return render(request, "app/trades.html", 
        {"trades": Trade.objects.filter(seller=investor).filter(buyer=investor)})
    else:
        return render(request, 'app/index.html')


