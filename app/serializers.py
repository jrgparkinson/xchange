from django.contrib.auth.models import User, Group
from app.models import *
from rest_framework import serializers, validators
import logging
from app.errors import AssetNotOwned

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
        fields = ['id'] #,'name']

    def to_representation(self, instance):
        return instance.id
        

class SeasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Season
        fields = ['id', 'status', 'name', 'start_time', 'end_time']


class ShareSerializer(serializers.ModelSerializer):
    athlete = serializers.PrimaryKeyRelatedField(queryset=Athlete.objects.all())
    owner = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all(), required=False, allow_null=True)
    is_virtual = serializers.BooleanField(read_only=True)

    class Meta:
        model = Share
        fields = ['id', 'asset_type', 'athlete', 'volume', 'owner', 'is_virtual']
        depth = 1

    def create(self, validated_data):
        LOGGER.info("Create share with: ")
        LOGGER.info(validated_data)
        share = Share(**validated_data)

        # Set virtual unless we decide otherwise
        if not 'is_virtual' in validated_data.keys():
            share.is_virtual = True

        if not 'season' in validated_data.keys():
            share.season = get_current_season()

        share.save()

        return share


class OptionSerializer(serializers.ModelSerializer):
    option_holder = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all())
    underlying_asset = ShareSerializer()
    seller = EntityIdSerializer(required=False, allow_null=True)
    buyer = EntityIdSerializer(required=False, allow_null=True)

    class Meta:
        model =  Option
        fields = ['id', 'asset_type', 'strike_price', 'strike_time',  'underlying_asset',
                   'seller',  'buyer', 'option_holder', 'current_option']
        depth = 1
        
    

class FutureSerializer(OptionSerializer):
    option_holder = None
    current_option = None

    def create(self, validated_data):

        future = Future(**validated_data)
        future.save()
        return future

  
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
            return ShareSerializer().to_internal_value(data)
        elif data["type"].lower() == "future":
            return FutureSerializer().to_internal_value(data)
        elif data["type"].lower() == "option":
            return OptionSerializer().to_internal_value(data)
        else:
            raise XChangeException("Unknown asset type {}".format(data["type"]))

    def get_serializer(data):
        LOGGER.info("get serializer with data: {}".format(data))
        if "type" in data.keys() and data["type"].lower() == "share" or "athlete" in data.keys():
            
            if isinstance(data["athlete"], Athlete):
                data["athlete"] = data["athlete"].id
            return ShareSerializer(data=data)
        elif "buyer" in data.keys() and "option_holder" in data.keys():
            return OptionSerializer(data=data) 
        elif "buyer" in data.keys():
            return FutureSerializer(data=data)
        else:
            raise XChangeException("Unknown asset type: {}".format(data))
        


class AssetSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ['id', 'asset_type']


class TradeSerializer(serializers.ModelSerializer):
    buyer = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all(), allow_null=True) #EntityIdSerializer()
    seller = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all(), allow_null=True)
    creator = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all(), allow_null=True, required=False)
    asset = AssetGenericSerializer()

    def create(self, validated_data):
        LOGGER.info("TradeSerializer create: " + str(validated_data))

        # Create asset to trade
        LOGGER.info(validated_data["asset"])
        asset_serializer = AssetGenericSerializer.get_serializer(validated_data["asset"]) # (data=request.data["asset"])
        
        if (asset_serializer.is_valid() == False):
            # return asset_serializer.errors
            LOGGER.info(asset_serializer.errors)
            return None
            
        asset = asset_serializer.save()
        asset.is_virtual = True
        asset.save()

        validated_data["asset"] = asset

        return self.save_with_fields_filled(validated_data)

    def validate(self, attrs):
        # TODO: need to make sure validation includes asset too, so validation errors
        # are properly returned to the client
        asset_serializer = AssetGenericSerializer.get_serializer(data["asset"]) # (data=request.data["asset"])
        asset_serializer.validate()
        if (asset_serializer.is_valid() == False):
            return asset_serializer.errors # , status=status.HTTP_400_BAD_REQUEST)



    def save_with_fields_filled(self, validated_data):
        trade = Trade(**validated_data)

        if not 'season' in validated_data.keys():
            trade.season = get_current_season()

        trade.save()
        return trade


    class Meta:
        model = Trade
        
        fields = ['id', 'asset', 'buyer', 'seller', 'creator', 
        'price', 'created','updated', 'status_detailed']

        
class TradeExistingAssetSerializer(TradeSerializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.all())

    def create(self, validated_data):
        LOGGER.info("TradeSerializer create: " + str(validated_data))

        return super().save_with_fields_filled(validated_data)

        # trade = Trade(**validated_data)

        # if not 'season' in validated_data.keys():
        #     trade.season = get_current_season()

        # trade.save()
        # return trade

class InvestorSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Investor
        fields = ['id', 'user']

class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank  
        fields = ['id', 'name']


class DebtSerializer(serializers.ModelSerializer):
    owed_by = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all())
    owed_to = serializers.PrimaryKeyRelatedField(queryset=Entity.objects.all())

    class Meta:
        model = Debt
        fields = ('id', 'owed_by', 'owed_to', 'created', 'ammount')