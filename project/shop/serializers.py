from rest_framework import serializers as sz
from shop.models import Item, UserItem, Jorang


class ItemSerializer(sz.ModelSerializer):
    class Meta:
        model = Item
        fields = [
            'id',
            'item_name',
            'item_type',
            'item_detail',
            'item_price',
            'released_at'
        ]


class UserItemSerializer(sz.ModelSerializer):

    def update(self, instance, validated_data):
        instance.is_worn = validated_data.get('is_worn', instance.is_worn)
        return instance

    def to_representation(self, instance):
        response = super().to_representation(instance)
        response['item'] = ItemSerializer(instance.item).data
        return response

    class Meta:
        model = UserItem
        fields = [
            'id',
            'profile',
            'item',
            'is_worn'
        ]


class JorangSerializer(sz.ModelSerializer):
    items = UserItemSerializer(read_only=True, many=True)

    class Meta:
        model = Jorang
        fields = [
            'id',
            'profile',
            'nickname',
            'items',
            'status',
            'title'
        ]

