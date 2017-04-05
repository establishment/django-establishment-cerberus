import os
import sys
import time

from establishment.services.service_daemon import ServiceDaemon


class CerberusDaemon(ServiceDaemon):

    def run(self):
        self.logger.info("Cerberus Daemon 1.0")
        self.logger.info("Operating system: " + os.name + " -- " + sys.platform)
        self.logger.info("File system encoding: " + sys.getfilesystemencoding())

        from cerberus.permission_checking_worker import UserIdentificationCommandProcessor
        from cerberus.permission_checking_worker import SubscriptionPermissionCommandProcessor
        from cerberus.permission_checking_worker import MetaStreamEventsCommandProcessor

        self.command_processors = [UserIdentificationCommandProcessor(), SubscriptionPermissionCommandProcessor(),
                                   MetaStreamEventsCommandProcessor()]
        for command_processor in self.command_processors:
            command_processor.start()

        while not self.terminate:
            time.sleep(1)
        self.logger.warning("Terminating")

        for command_processor in self.command_processors:
            command_processor.stop()
