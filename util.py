import inspect
import os
import sys

def add_lib_path(lib_dir):
    lib_dir = os.path.realpath(os.path.abspath(os.path.join(os.path.split(inspect.getfile( inspect.currentframe() ))[0],lib_dir)))
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
