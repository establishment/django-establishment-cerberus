import os
import sys
import time

from establishment.services.service_daemon import ServiceDaemon


class CerberusDaemon(ServiceDaemon):
    def setup_logging(self):
        # TODO: WHY DOES THIS WORK??? FIX IT IN ESTABLISHMENT
        pass

    def run(self):
        self.logger.info("Cerberus Daemon 1.0")
        self.logger.info("Operating system: " + os.name + " -- " + sys.platform)
        self.logger.info("File system encoding: " + sys.getfilesystemencoding())

        from establishment.misc.command_processor import CommandProcessorHandler
        from cerberus.permission_checking_worker import UserIdentificationCommandProcessor
        from cerberus.permission_checking_worker import SubscriptionPermissionCommandProcessor
        from cerberus.permission_checking_worker import MetaStreamEventsCommandProcessor

        self.command_processor_handler = CommandProcessorHandler([UserIdentificationCommandProcessor("cerberus"),
                                                                  SubscriptionPermissionCommandProcessor("cerberus"),
                                                                  MetaStreamEventsCommandProcessor("cerberus")])

        self.command_processor_handler.start()

        while not self.terminate:
            time.sleep(1)
        self.logger.warning("Terminating")

        self.command_processor_handler.stop()

        self.command_processor_handler.wait_to_finish()
