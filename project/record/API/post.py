from datetime import date, timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.datastructures import MultiValueDictKeyError

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes

from config.permissions import MyIsAuthenticated, IsOwnedByProfile
from core.models import UserCoin, Attendance, Profile
from core.ERROR.error_cases import GlobalErrorMessage, GlobalErrorMessage400
from core.API.jorang import upgrade_jorang_status
from record.API.utils import pick_question_pk_number, calculate_continuity_and_reward, update_user_coin_with_reward, \
    get_question_of_user_question, fix_image_name
from record.models import Post, Question, UserQuestion
from record.serializers import PostSerializer, UserQuestionSerializer


# /posts/questions/
@api_view(['GET'])
@permission_classes([MyIsAuthenticated, ])
def everyday_user_question_generation(request):
    """
        매일 사람들에게 개인별로 Question 을 생성을 해주기 위해서 만든 API 입니다.
        model Question 에 관리자가 넣어둔 question 들중 하나를 들고온다.
        그리고 그것을 user_question 에 update 한다.

        TODO: 질문이 안 바뀐다? -> 그러면 식상 할 것 같으니, 유저가 똑같은 질문을 받지 않게 짜야한다.
        TODO: 다음 버젼 고쳐봐야겠다.
    """
    email = request.user.email
    profile = Profile.objects.get(email=email)
    user_question = UserQuestion.objects.get(profile=profile.pk)

    # 새로 생성을 하거나 or 오늘 처음 question 생성하는 경우.
    # 오늘 생성을 할경우, last_login 이 created 되어 버리기 때문에, question 이 존재 하지 않으면, 생성
    if user_question.last_login != date.today() or user_question.question is None:
        question_pk = pick_question_pk_number()
        if question_pk == 0:
            raise GlobalErrorMessage400("행복 질문이 존재하지 않습니다. 행복 질문 등록 후 이용하세요")
        try:
            new_question = Question.objects.get(pk=question_pk)
            user_question.question = new_question
            user_question.save()
        except (Question.DoesNotExist, AssertionError):
            raise GlobalErrorMessage400("행복 질문이 존재하지 않습니다. 행복 질문 등록 후 이용하세요")

    question = UserQuestion.objects.filter(profile=request.user.pk)
    sz = UserQuestionSerializer(question, many=True)
    return Response(sz.data)


# TODO : naming 고치기
class PostView(APIView):
    permission_classes = [MyIsAuthenticated, ]
    parser_classes = (FormParser, MultiPartParser,)
    serializer_class = PostSerializer

    def get(self, request):
        """
            get 에서
            http://{{ip}}:{{port}}/record/posts/?search_fields=created_at&search=2020-08-16
            위와 같이, search_fields 와 search 를 사용을 하여,
            Post.objects.all().filter(**filter_dictionary)
            와 같이 필터링 가능할수 있도록 구현을 하였습니다.

            detail 일 경우에는 포함을 하는 경우가 있으면, 그 POST 를 찾아서 돌려 줍니다.
        """

        search_fields = request.GET.getlist('search_fields', [])
        search_values = request.GET.getlist('search', [])
        # URL 에서 잘못 된 경우
        if len(search_fields) != len(search_values):
            raise GlobalErrorMessage400(
                "search_fields 와 search 가 mapping 이 되지 않습니다. 확인해주세요")

        filter_dictionary = {"profile": self.request.user.pk}
        detail_value = "if somebody try this, that person intend to do that"
        if "detail" in search_fields:
            for i in range(0, len(search_fields)):
                if search_fields[i] == "detail":
                    detail_value = search_values[i]
                    continue
                filter_dictionary[search_fields[i]] = search_values[i]
            filter_post = Post.objects.filter(**filter_dictionary, detail__contains=detail_value)

        else:
            # TODO : enumerator 라고 바꾸는 게 좀더 pythonic 하다.
            for i in range(0, len(search_fields)):
                filter_dictionary[search_fields[i]] = search_values[i]
            filter_post = Post.objects.filter(**filter_dictionary)

        sz = PostSerializer(filter_post, many=True)
        return Response(sz.data)

    def post(self, request):
        """
            하루에 한번만 새로운 Post 를 작성할 수 있는 기능으로,
            emotion, detail, image 를 request 를 통해 받아서 Post model 에 넣어줍니다.
            이를 통해, reward 와 continuity 를 계산하여, user_coin 의 값을 Update 할 수 있습니다
        """

        email = request.user.email
        profile = Profile.objects.get(email=email)
        user_coin = UserCoin.objects.get(profile=profile.pk)

        data = request.data
        _mutable = data._mutable
        data._mutable = True
        data['profile'] = email
        data['question'] = get_question_of_user_question(profile_pk=profile.pk)
        try:
            request.data["image"].name = fix_image_name(
                image_name=request.data["image"].name)
        except MultiValueDictKeyError:
            pass

        # 연속 기록 체크
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        continuity, reward = calculate_continuity_and_reward(profile_pk=profile.pk,
                                                             created_at=yesterday,
                                                             today=today,
                                                             tomorrow=tomorrow)

        data['continuity'] = continuity
        data._mutable = _mutable
        post_serializer = PostSerializer(data=data)
        # 이미 요기서 created_at 이 unique 이기 때문에, 하루에 중복되는 생성은 일어나지 않는다.
        if not post_serializer.is_valid():
            raise GlobalErrorMessage400(str(post_serializer.errors))

        post_serializer.save()
        Attendance.objects.create(
            profile=profile,
            date=today,
            emotion=data['emotion'])

        coin: int = update_user_coin_with_reward(
            user_coin=user_coin, reward=reward, today=today)

        if continuity > 0 and continuity % 10 == 0:
            upgrade_jorang_status(profile)

        return Response({
            "response": "success",
            "message": "성공적으로 일기를 업로드하였습니다.",
            "post_detail": post_serializer.data,
            "reward_detail": {
                "reward_of_today": reward,
                "coin": coin,
                "continuity": continuity
            }}, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------------

class PostDetail(APIView):
    """
    Retrieve a happy-record instance for a specific date
    """
    permission_classes = (MyIsAuthenticated, IsOwnedByProfile,)

    def get_object(self, pk):
        """
            Object level permission:
            get_object() --> check_object_permissions --> permission_classes --> config.permissions.IsOwnedByProfile
        """
        obj = get_object_or_404(Post.objects.all(), pk=self.kwargs["pk"])
        self.check_object_permissions(self.request, obj)
        return obj

    def get(self, request, pk, format=None):
        """
            pk 를 통해서, Post 객체에 접근을 한다.
            만약 내가 작성 or 관리자일 경우에는 접근이 가능하고,
            다른 사람의 작성물일 경우 볼 수 없다.
        """

        email = request.user.email
        profile = Profile.objects.get(email=email)

        post = self.get_object(pk)
        post_serializer = PostSerializer(post)

        return Response(post_serializer.data)

    def patch(self, request, pk, format=None):
        """
            form-data 에 detail, emotion, image 를
            input 으로 넣어준다.
            그리고, 그것을 PostSerializer 에서 update 를 통해서 갱신을 한다.
        """
        post = self.get_object(pk)

        email = request.user.email
        profile = Profile.objects.get(email=email)
        # 이름의 확장자가 jpg" 으로 되는 경우가 있어서, 수정을 하였다.
        try:
            request.data["image"].name = fix_image_name(
                image_name=request.data["image"].name)
        except MultiValueDictKeyError:
            pass

        post_serializer = PostSerializer(post, data=request.data, partial=True)
        if post_serializer.is_valid():
            post_serializer.save()
            return Response({
                "response": "success",
                "message": "성공적으로 수정하였습니다."})
        raise GlobalErrorMessage400(str(post_serializer.errors))

    def delete(self, request, pk, format=None):
        post = self.get_object(pk)
        email = request.user.email
        profile = Profile.objects.get(email=email)
        user_coin = UserCoin.objects.get(profile=profile.id)

        if post.created_at == user_coin.last_date:
            raise GlobalErrorMessage("마지막 기록은 지울 수 없습니다.")
        post.delete()
        return Response({
            'response': 'success',
            'message': '기록을 삭제하였습니다.'
        }, status=status.HTTP_204_NO_CONTENT)
