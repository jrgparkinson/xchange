from django.contrib.auth.models import User, Group
from app.models import Trade, Asset, Entity, Season
from rest_framework import viewsets, status
from app.serializers import *
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
import logging
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework import permissions

LOGGER = logging.getLogger(__name__)



@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'trades': reverse('trades-list', request=request, format=format),
        'athletes': reverse('athletes-list', request=request, format=format),
        'entities': reverse('entity-list', request=request, format=format),
        'assets': reverse('asset-list', request=request, format=format),
        'current_user': reverse('current_user', request=request, format=format),
        'debts': reverse('debt-list', request=request, format=format),
        # 'debt': reverse('debt-detail', request=request, format=format, args=[]),
        # 'contracts': reverse('entity-list', request=request, format=format),
    })  


@api_view(['GET'])
def current_user(request):
    serializer = EntitySerializer(request.user.investor)
    return Response(serializer.data)


class TradeList(generics.ListCreateAPIView):
    serializer_class = TradeSerializer

    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def create(self, request, *args, **kwargs): # don't need to `self.request` since `request` is available as a parameter.

        """
        Example JSON:
        {
            "asset": {"type":"share", "athlete": 4, "volume": 1.05},
            "buyer": null,
            "seller": 1,
            "price": 42.0
        }
        """

        # Asset can either be an int (primary key) or a representation of a new (virtual) asset to trade
        # So that trade serializer validation works
        asset = request.data["asset"]
        if isinstance(asset, int):
            trade_serializer = TradeExistingAssetSerializer(data=request.data)

        else:
            # Create asset too
            trade_serializer = TradeSerializer(data=request.data)
       
        
        if (trade_serializer.is_valid() == False):
            return Response(trade_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        trade = trade_serializer.save(creator=request.user.investor)

        LOGGER.info("Created trade: {}".format(trade))

        return Response({"response": "success"}) # `respo

    def get_queryset(self):
        queryset = Trade.objects.all().order_by("-updated")
        
        asset_type = self.request.query_params.get('asset', None)
        if asset_type:
            queryset = [q for q in queryset if q.asset.asset_type.lower() == asset_type.lower()]

        athlete_id = self.request.query_params.get('athlete_id', None)
        if athlete_id:
            queryset = [q for q in queryset if q.asset.is_share() and q.asset.share.athlete.id == int(athlete_id)]

        return queryset


class AthleteList(generics.ListAPIView):
    queryset = Athlete.objects.all()
    serializer_class = AthleteSerializer

class Athlete(generics.RetrieveAPIView):
    queryset = Athlete.objects.all()
    serializer_class = AthleteDetailedSerializer

class EntityList(generics.ListAPIView):
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer

class Entity(generics.RetrieveAPIView):
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer

# TODO: change to ListAPIView
class AssetList(generics.ListCreateAPIView):
    serializer_class = AssetGenericSerializer

    def get_queryset(self):
        queryset = Asset.objects.all().order_by('id')
        
        asset_type = self.request.query_params.get('type', None)
        if asset_type:
            queryset = [q for q in queryset if q.asset_type.lower() == asset_type.lower()]

        athlete_id = self.request.query_params.get('athlete_id', None)
        if athlete_id:
            queryset = [q for q in queryset if q.is_share() and q.share.athlete.id == int(athlete_id)]

        owner_id = self.request.query_params.get('owner', None)
        if owner_id:
            queryset = [q for q in queryset if q.owner and q.owner.id == int(owner_id)]


        return queryset


    def create(self, request, *args, **kwargs): 

        # Create asset to trade
        asset_serializer = AssetGenericSerializer.get_serializer(request.data) # (data=request.data["asset"])
        if (asset_serializer.is_valid() == False):
            return Response(asset_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        asset = asset_serializer.save()

        LOGGER.info("Create asset: {}, id={}".format(asset, asset.id))

        return Response({"response": "success"})


    

class AssetRetrieve(generics.RetrieveAPIView):
    queryset = Asset.objects.all()
    serializer_class = AssetGenericSerializer



class IsDebtOwedByOrReadOnly(permissions.BasePermission):
     def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the user who owes the debt
        # LOGGER.info(obj)
        # LOGGER.info(obj.owed_by)
        # LOGGER.info(request.user)
        # LOGGER.info(obj.owed_by == request.user.investor)
        return obj.owed_by == request.user.investor

class DebtViewSet(viewsets.ModelViewSet):
    serializer_class = DebtSerializer
    queryset = Debt.objects.all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly,
                          IsDebtOwedByOrReadOnly]

    


debt_list = DebtViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

debt_detail = DebtViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    # 'delete': 'destroy'
})

    