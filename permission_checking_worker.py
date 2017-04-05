import json
import logging
import time

from django.contrib.auth import get_user, get_user_model

from establishment.chat.models import GroupChat, PrivateChat
from establishment.detoate.threading_helper import ThreadHandler
from establishment.funnel.nodews_meta import NodeWSMeta
from establishment.funnel.redis_stream import RedisStreamPublisher, RedisStreamSubscriber
from establishment.funnel.permission_checking import user_can_subscribe_to_stream, guest_can_subscribe_to_stream

logger = logging.getLogger("cerberus")

# TODO: Use the default Django session engine
import redis_sessions.session as session_engine


class BaseCommandProcessor(object):
    def __init__(self):
        self.background_thread = None
        self.keep_working = True

    def get_next_command(self):
        raise RuntimeError("Implement me!")

    def process_command(self, command):
        raise RuntimeError("Implement me!")

    def publish_answer(self, answer, command):
        raise RuntimeError("Implement me!")

    def handle_exception(self, exception):
        if hasattr(self, "logger"):
            self.logger.exception("Exception in command processor " + str(self.name))

    def process(self):
        logger.info("Starting to process commands " + str(self.__class__.__name__))

        while self.keep_working:
            try:
                command = self.get_next_command()
                if command:
                    answer = self.process_command(command)
                    if answer:
                        self.publish_answer(answer, command)
            except Exception as exception:
                self.handle_exception(exception)

    def start(self):
        self.background_thread = ThreadHandler("Command processor " + str(self.__class__.__name__), self.process)

    def stop(self):
        self.keep_working = False


class BaseRedisCommandProcessor(BaseCommandProcessor):
    def __init__(self, redis_stream_name):
        super().__init__()
        self.redis_stream_name = redis_stream_name
        self.redis_stream_subscriber = None
        self.redis_stream_publisher = None

    def get_next_command(self):
        if not self.redis_stream_subscriber:
            self.redis_stream_subscriber = RedisStreamSubscriber()
            self.redis_stream_subscriber.subscribe(self.redis_stream_name + "-q")
            self.redis_stream_publisher = RedisStreamPublisher(self.redis_stream_name + "-a", raw=True)

        message, stream_name = self.redis_stream_subscriber.next_message()

        if not message:
            return message

        try:
            message = str(message, "utf-8")
        except Exception as e:
            logger.error("Failed to convert to unicode")
            return None

        try:
            return json.loads(message)
        except Exception as e:
            logger.error("Failed to parse command " + str(message))
            return None

    def publish_answer(self, answer, command):
        self.redis_stream_publisher.publish_json(answer)

    def handle_exception(self, exception):
        logger.exception("Error processing redis command for " + str(self.__class__.__name__))
        self.redis_stream_subscriber = None
        self.redis_stream_publisher = None
        time.sleep(1.0)


class SubscriptionPermissionCommandProcessor(BaseRedisCommandProcessor):
    def __init__(self):
        super().__init__("meta-subscription-permissions")

    def process_command(self, command):
        if "userId" not in command:
            logger.error("Invalid user identification request: no userId field!")
            return {
                "canRegister": False,
                "reason": "Invalid Cerberus request!",
                "streamName": "INVALID_STREAM_NAME",
                "userId": -1
            }
        user_id = command["userId"]

        if "streamName" not in command:
            logger.error("Invalid user identification request: no streamName field! ")
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
        except Exception as e:
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
    def __init__(self):
        super().__init__("meta-user-identification")

    def process_command(self, command):
        if "sessionKey" not in command:
            logger.error("Invalid user identification request: no sessionKey found! ")
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
    def __init__(self):
        super().__init__("meta-stream-events")
        self.meta = NodeWSMeta()

    def process_command(self, command):
        if command["command"] == "fullUpdate":
            self.full_update()
        elif command["command"] == "streamEvent":
            if command["event"] == "joined":
                self.broadcast_join_event(command["stream"], command["userId"])
            elif command["event"] == "left":
                self.broadcast_left_event(command["stream"], command["userId"])

        return None

    def full_update(self):
        streams = self.meta.get_streams()

        for stream in streams:
            if stream_need_online_users(stream):
                self.update_stream_users(stream)

    def update_stream_users(self, stream):
        users = self.meta.get_online_users(stream)

        data = {
            "online": users
        }

        event = {
            "objectType": "messagethread",
            "type": "online",
            "objectId": stream_message_thread_get_id(stream),
            "data": data,
        }

        RedisStreamPublisher.publish_to_stream(stream, event)

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
