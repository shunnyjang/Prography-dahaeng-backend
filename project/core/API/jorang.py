from datetime import date, timedelta

from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes

from config.permissions import MyIsAuthenticated
from config.utils import random_color
from core.ERROR.error_cases import GlobalErrorMessage
from shop.models import Jorang, UserItem, Item


# /jorang/
@api_view(['POST'])
@permission_classes([MyIsAuthenticated, ])
def create(request):
    """
        우리의 마스코트 조랭이
        조랭이의 경우, 생성될 때, 유저와 1:1 [OneToOneField] 로 mapping 이 되기 떄문에
        유저(Profile) 당 딱 한번 밖에 생성이 되지 않는다.
        그렇기에 유의를 할 필요가 있다.
        {
            "nickname": "산림수"
        }

        1. Jorang 생성
            -> 조랭이는 profile 당 하나만 생성을 할 수 있다.
        2. UserItem 과 Jorang 의 color 를 의미하는 Item 과 매칭.
            -> Item 에 jorang_color 라는 item 객체들이 있고,
            이를 UserItem 을 통해서, User 가 구입한 Item 으로 하나 만들어 주는 것이다.(스타트 보너스)
            -> 만약 아이템이 존재 하지 않을 경우, 조랭이 생성에 실패한다. 미리미리 상점에 Upload 하자.

    """
    try:
        nickname = request.data['nickname']
    except KeyError:
        raise GlobalErrorMessage('request body 의 파라미터가 잘못되었습니다.')

    profile = request.user

    if is_jorang_exist(profile_pk=profile.pk):
        raise GlobalErrorMessage('이미 조랭이를 가지고 있는 계정입니다.')

    color, background = add_jorang_default_items(profile)

    user_jorang = Jorang.objects.create(
        nickname=nickname,
        profile=profile
    )
    user_jorang.items.add(color)
    user_jorang.items.add(background)

    return Response({
        'response': 'success',
        'message': 'Jorang이 성공적으로 생성되었습니다.'
    })


def is_jorang_exist(profile_pk):
    try:
        Jorang.objects.get(profile=profile_pk)
        return True
    except Jorang.DoesNotExist:
        return False


def add_jorang_default_items(profile):
    color = random_color()
    back = Item.objects.get(item_type="background", item_detail="background-ground")

    default_color = UserItem.objects.create(profile=profile, item=color, is_worn=True)
    default_back = UserItem.objects.create(profile=profile, item=back, is_worn=True)

    return default_color, default_back


def upgrade_jorang_status(profile):
    try:
        jorang = Jorang.objects.get(profile=profile)
        if jorang.status == 0:
            jorang.status = 1
        elif jorang.status == 1:
            jorang.status = 2
        jorang.save()
        return jorang.status
    except Jorang.DoesNotExist:
        raise GlobalErrorMessage("유저에게 조랭이가 없습니다!!")


def downgrade_jorang_status(profile):
    if profile.post.last() is None:
        return 
        # raise GlobalErrorMessage("유저에게 작성된 일기가 없습니다!!")

    last_post_date = profile.post.last().created_at
    timedelta_last_post_and_today = date.today() - last_post_date

    if timedelta_last_post_and_today > timedelta(days=5):
        try:
            jorang = Jorang.objects.get(profile=profile)
            if int(jorang.status) > 0:
                jorang.status = str(int(jorang.status) - 1)
                jorang.save()
        except Jorang.DoesNotExist:
            raise GlobalErrorMessage("유저에게 조랭이가 없습니다!!")
