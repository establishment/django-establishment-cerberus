from django.contrib.auth import get_user, get_user_model

from establishment.funnel.utils import DBObjectStoreWithNull
from establishment.chat.models import GroupChat, PrivateChat
from establishment.funnel.permission_checking import user_can_subscribe_to_stream, guest_can_subscribe_to_stream
from establishment.funnel.redis_stream import RedisStreamPublisher
from establishment.misc.greenlet_workers import GreenletRedisQueueCommandProcessor, GreenletQueueWorker

# TODO: Use the default Django session engine
import redis_sessions.session as session_engine

GREENLET_JOB_QUEUE_MAX_SIZE = 4 * 1024
GREENLET_WORKERS_THREAD = 64


class GreenletSubscriptionPermissionWorker(GreenletQueueWorker):
    def __init__(self, job_queue=None, result_queue=None, logger=None, context=None):
        super().__init__(job_queue=job_queue, result_queue=result_queue, logger=logger, context=context)
        self.user_cache = context["userCache"]

    def process_command(self, command):
        if "responseStream" not in command:
            self.error("Invalid user identification request: no responseStream field!")
            return

        response_stream = command["responseStream"]

        if "userId" not in command:
            self.error("Invalid user identification request: no userId field!")
            RedisStreamPublisher.publish_to_stream(message={
                "canRegister": False,
                "reason": "Invalid Cerberus request!",
                "streamName": "INVALID_STREAM_NAME",
                "userId": -1
            }, stream_name=response_stream, raw=True)
            return
        user_id = command["userId"]

        if "streamName" not in command:
            self.error("Invalid user identification request: no streamName field! ")
            RedisStreamPublisher.publish_to_stream(message={
                "canRegister": False,
                "reason": "Invalid Cerberus request!",
                "streamName": "INVALID_STREAM_NAME",
                "userId": user_id
            }, stream_name=response_stream, raw=True)
        stream_name = command["streamName"]

        if user_id == 0:
            can_register = guest_can_subscribe_to_stream(stream_name)
        else:
            user = self.user_cache.get(id=user_id)
            can_register = user_can_subscribe_to_stream(user, stream_name)
        try:
            can_register, reason = can_register
        except Exception:
            reason = "Default"
        RedisStreamPublisher.publish_to_stream(message={
            "canRegister": can_register,
            "reason": reason,
            "streamName": stream_name,
            "userId": user_id
        }, stream_name=response_stream, raw=True)


class SubscriptionPermissionCommandProcessor(GreenletRedisQueueCommandProcessor):
    def __init__(self, logger_name):
        super().__init__(logger_name, GreenletSubscriptionPermissionWorker, "meta-subscription-permissions",
                         num_workers=GREENLET_WORKERS_THREAD, job_queue_max_size=GREENLET_JOB_QUEUE_MAX_SIZE)
        self.worker_context = {
            "userCache": DBObjectStoreWithNull(get_user_model(), default_max_age=30)
        }


class OurRequest(object):
    def __init__(self):
        self.session = dict()


class GreenletUserIdentificationWorker(GreenletQueueWorker):
    def process_command(self, command):
        if "responseStream" not in command:
            self.error("Invalid user identification request: no responseStream field!")
            return

        response_stream = command["responseStream"]

        if "sessionKey" not in command:
            self.logger.error("Invalid user identification request: no sessionKey found! ")
            RedisStreamPublisher.publish_to_stream(message={
                "sessionKey": "INVALID_SESSION_KEY",
                "userId": -1
            }, stream_name=response_stream, raw=True)
        session_key = command["sessionKey"]

        request = OurRequest()
        request.session = session_engine.SessionStore(session_key)

        user = get_user(request)

        user_id = -1
        if user and user.is_authenticated:
            user_id = user.id

        RedisStreamPublisher.publish_to_stream(message={
            "sessionKey": session_key,
            "userId": user_id,
        }, stream_name=response_stream, raw=True)


class UserIdentificationCommandProcessor(GreenletRedisQueueCommandProcessor):
    def __init__(self, logger_name):
        super().__init__(logger_name, GreenletUserIdentificationWorker, "meta-user-identification",
                         num_workers=GREENLET_WORKERS_THREAD, job_queue_max_size=GREENLET_JOB_QUEUE_MAX_SIZE)


def stream_need_online_users(stream):
    return GroupChat.matches_stream_name(stream)


def stream_message_thread_get_id(stream):
    if GroupChat.matches_stream_name(stream):
        return int(GroupChat.stream_name_pattern.split(stream)[2])
    if PrivateChat.matches_stream_name(stream):
        return int(PrivateChat.stream_name_pattern.split(stream)[3])
    return -1


class GreenletMetaStreamEventsWorker(GreenletQueueWorker):
    def process_command(self, command):
        if command["command"] == "streamEvent":
            if command["event"] == "joined":
                self.broadcast_join_event(command["stream"], command["userId"])
            elif command["event"] == "left":
                self.broadcast_left_event(command["stream"], command["userId"])

        return None

    def broadcast_join_event(self, stream, user_id):
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

    def broadcast_left_event(self, stream, user_id):
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


class MetaStreamEventsCommandProcessor(GreenletRedisQueueCommandProcessor):
    def __init__(self, logger_name):
        super().__init__(logger_name, GreenletMetaStreamEventsWorker, "meta-stream-events",
                         num_workers=GREENLET_WORKERS_THREAD, job_queue_max_size=GREENLET_JOB_QUEUE_MAX_SIZE)
