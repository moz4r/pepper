# -*- coding: utf-8 -*-
# classSystem.py — Couleurs pour la console et gestion de version
import os
import io

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class version(object):
    _here = os.path.dirname(os.path.abspath(__file__))
    version_path = os.path.join(_here, "version")

    @classmethod
    def get(cls, default=u"dev"):
        try:
            if os.path.isfile(cls.version_path):
                with io.open(cls.version_path, "r", encoding="utf-8") as f:
                    return f.read().strip() or default
        except Exception:
            pass
        return default
