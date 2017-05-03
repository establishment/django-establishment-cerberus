from django.contrib.auth import get_user, get_user_model

from establishment.chat.models import GroupChat, PrivateChat
from establishment.funnel.nodews_meta import NodeWSMeta
from establishment.funnel.permission_checking import user_can_subscribe_to_stream, guest_can_subscribe_to_stream
from establishment.funnel.redis_stream import RedisStreamPublisher
from establishment.misc.command_processor import BaseRedisCommandProcessor

# TODO: Use the default Django session engine
import redis_sessions.session as session_engine


class SubscriptionPermissionCommandProcessor(BaseRedisCommandProcessor):
    def __init__(self, logger_name):
        super().__init__(logger_name, "meta-subscription-permissions")

    def process_command(self, command):
        if "userId" not in command:
            self.logger.error("Invalid user identification request: no userId field!")
            return {
                "canRegister": False,
                "reason": "Invalid Cerberus request!",
                "streamName": "INVALID_STREAM_NAME",
                "userId": -1
            }
        user_id = command["userId"]

        if "streamName" not in command:
            self.logger.error("Invalid user identification request: no streamName field! ")
            return {
                "canRegister": False,
                "reason": "Invalid Cerberus request!",
                "streamName": "INVALID_STREAM_NAME",
                "userId": user_id
            }
        stream_name = command["streamName"]

        if user_id == 0:
            can_register = guest_can_subscribe_to_stream(stream_name)
        else:
            UserModel = get_user_model()
            user = UserModel.objects.get(id=user_id)
            can_register = user_can_subscribe_to_stream(user, stream_name)
        try:
            can_register, reason = can_register
        except Exception:
            reason = "Default"
        return {
            "canRegister": can_register,
            "reason": reason,
            "streamName": stream_name,
            "userId": user_id
        }


class OurRequest(object):
    def __init__(self):
        self.session = dict()


class UserIdentificationCommandProcessor(BaseRedisCommandProcessor):
    def __init__(self, logger_name):
        super().__init__(logger_name, "meta-user-identification")

    def process_command(self, command):
        if "sessionKey" not in command:
            self.logger.error("Invalid user identification request: no sessionKey found! ")
            return {
                "sessionKey": "INVALID_SESSION_KEY",
                "userId": -1
            }
        session_key = command["sessionKey"]

        request = OurRequest()
        request.session = session_engine.SessionStore(session_key)

        user = get_user(request)

        user_id = -1
        if user and user.is_authenticated():
            user_id = user.id

        return {
            "sessionKey": session_key,
            "userId": user_id,
        }


def stream_need_online_users(stream):
    return GroupChat.matches_stream_name(stream)


def stream_message_thread_get_id(stream):
    if GroupChat.matches_stream_name(stream):
        return int(GroupChat.stream_name_pattern.split(stream)[2])
    if PrivateChat.matches_stream_name(stream):
        return int(PrivateChat.stream_name_pattern.split(stream)[3])
    return -1


class MetaStreamEventsCommandProcessor(BaseRedisCommandProcessor):
    def __init__(self, logger_name):
        super().__init__(logger_name, "meta-stream-events")
        self.meta = NodeWSMeta()

    def process_command(self, command):
        if command["command"] == "streamEvent":
            if command["event"] == "joined":
                self.broadcast_join_event(command["stream"], command["userId"])
            elif command["event"] == "left":
                self.broadcast_left_event(command["stream"], command["userId"])

        return None

    @staticmethod
    def broadcast_join_event(stream, user_id):
        if not stream_need_online_users(stream):
            return

        data = {
            "userId": user_id
        }

        event = {
            "objectType": "messagethread",
            "type": "onlineDeltaJoined",
            "objectId": stream_message_thread_get_id(stream),
            "data": data,
        }

        RedisStreamPublisher.publish_to_stream(stream, event, persistence=False)

    @staticmethod
    def broadcast_left_event(stream, user_id):
        if not stream_need_online_users(stream):
            return

        data = {
            "userId": user_id
        }

        event = {
            "objectType": "messagethread",
            "type": "onlineDeltaLeft",
            "objectId": stream_message_thread_get_id(stream),
            "data": data,
        }

        RedisStreamPublisher.publish_to_stream(stream, event, persistence=False)
