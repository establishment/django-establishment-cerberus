from gevent import monkey
monkey.patch_all()

from psycogreen.gevent import patch_psycopg
patch_psycopg()

import os
import sys

establishment_path = None
new_sys_argv = []
for arg in sys.argv:
    if arg.startswith("--establishment-path="):
        establishment_path = arg[len("--establishment-path="):]
    else:
        new_sys_argv.append(arg)

sys.argv.clear()
sys.argv += new_sys_argv

if establishment_path:
    sys.path.insert(1, establishment_path)

parent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(1, parent_dir)

from cerberus.service import CerberusDaemon

daemon = CerberusDaemon("cerberus")
daemon.execute_command()
