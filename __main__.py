import os
import sys

parent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(1, parent_dir)

from cerberus.service import CerberusDaemon

daemon = CerberusDaemon("cerberus")
daemon.execute_command()