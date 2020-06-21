from django.contrib.auth.models import User, Group
from app.models import *
from rest_framework import serializers
import logging

LOGGER = logging.getLogger(__name__)

class ClubSerializer(serializers.ModelSerializer):
    class Meta:
        model =  Club
        fields = ['id', 'name']



class AthleteDetailedSerializer(serializers.ModelSerializer):
    club = ClubSerializer(many=False, read_only=True)


    class Meta:
        model =  Athlete
        fields = ['id', 'name', 'power_of_10', 'club', 'historical_values']

class AthleteSerializer(serializers.ModelSerializer):
    club = ClubSerializer(many=False, read_only=True)

    class Meta:
        model =  Athlete
        fields = ['id', 'name', 'power_of_10', 'club']


class EntitySerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Entity
        fields = ['id','name', 'portfolio']

class EntityIdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = ['id','name']

class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ['id', 'status', 'name', 'start_time', 'end_time']


class ShareSerializer(serializers.ModelSerializer):
    # athlete = AthleteSerializer(many=False)
    athlete = serializers.PrimaryKeyRelatedField(queryset=Athlete.objects.all())

    class Meta:
        model = Share
        fields = ['id', 'asset_type', 'athlete', 'volume']
        depth = 1

    def create(self, validated_data):
        LOGGER.info("Create share with: ")
        LOGGER.info(validated_data)
        share = Share(**validated_data)

        if not 'season' in validated_data.keys():
            share.season = get_current_season()

        share.save()

        return share



class OptionSerializer(serializers.ModelSerializer):
    option_holder = EntityIdSerializer()
    underlying_asset = ShareSerializer()
    seller = EntityIdSerializer()
    buyer = EntityIdSerializer()

    class Meta:
        model =  Option
        fields = ['id', 'asset_type', 'strike_price', 'strike_time',  'underlying_asset',
                   'seller',  'buyer', 'option_holder', 'current_option']
        depth = 1

class FutureSerializer(OptionSerializer):
    option_holder = None
    current_option = None


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ['id', 'asset_type', 'asset_type', 'owner', 'is_virtual', 'season']


class AssetGenericSerializer(serializers.Serializer):
    """ Serializer that renders each instance with its own specific serializer """

    def to_representation(self, instance):
        if instance.is_share():
            return ShareSerializer(instance=instance.share).data
        elif instance.is_future():
            return FutureSerializer(instance=instance.contract.future).data
        elif instance.is_option():
            return OptionSerializer(instance=instance.contract.future.option).data
        else:
            return AssetSerializer(instance=instance).data


    def to_internal_value(self, data):
        if data["type"].lower() == "share":
            return ShareSerializer().to_internal_value(data) # .to_internal_value(data)
        # elif data["type"].lower() == "future":
        #     return FutureSerializer.to_internal_value(data)
        # elif data["type"].lower() == "option":
        #     return OptionSerializer.to_internal_value(data)
        else:
            raise XChangeException("Unknown asset type {}".format(data["type"]))

    def get_serializer(data):
        LOGGER.info("get serializer with data: {}".format(data))
        if data["type"].lower() == "share":
            # athlete = Athlete.objects.get(pk=data["athlete"])
            return ShareSerializer(data=data)
        else:
            raise XChangeException("Unknown asset type {}".format(data["type"]))
        


class AssetSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ['id', 'asset_type']


class TradeSerializer(serializers.ModelSerializer):
    buyer = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all())
 #EntityIdSerializer()
    seller = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all())
    creator = EntityIdSerializer(read_only=True)
    asset = AssetGenericSerializer() # AssetSimpleSerializer()

    def create(self, validated_data):
        return Trade(**validated_data)

    class Meta:
        model = Trade
        
        fields = ['id', 'asset', 'buyer', 'seller', 'creator', 
        'price', 'created','updated', 'status_detailed']

class InvestorSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Investor
        fields = ['id', 'user']

class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank  
        fields = ['id', 'name']


