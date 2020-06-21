from django.contrib.auth.models import User, Group
from app.models import Trade, Asset, Entity, Season
from rest_framework import viewsets, status
from app.serializers import *
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
import logging

LOGGER = logging.getLogger(__name__)

@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'trades': reverse('trades-list', request=request, format=format),
        'athletes': reverse('athletes-list', request=request, format=format),
        'entities': reverse('entity-list', request=request, format=format),
        'assets': reverse('asset-list', request=request, format=format),
        # 'contracts': reverse('entity-list', request=request, format=format),
    })  

class TradeList(generics.ListCreateAPIView):
    serializer_class = TradeSerializer

    def create(self, request, *args, **kwargs): # don't need to `self.request` since `request` is available as a parameter.

        # your custom implementation goes here
        asset = request.data["asset"]

        # Check if we're trading an existing asset
        if 'id' in asset.keys():
            asset = Asset.objects.get(pk=request.data["asset"]["id"])

            # Check asset held by owner
            if not asset.owner == request.user: 
                raise PermissionError

        else:
            # Create asset to trade
            asset_serializer = AssetGenericSerializer.get_serializer(request.data["asset"]) # (data=request.data["asset"])
            if (asset_serializer.is_valid() == False):
                return Response(asset_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            asset = asset_serializer.save()

        LOGGER.info("Create trade with asset: {}".format(asset))

        return Response({"response": "success"}) # `respo

    def get_queryset(self):
        queryset = Trade.objects.all()
        
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


