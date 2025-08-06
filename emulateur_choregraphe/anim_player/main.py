#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import qi
from xar_player import XarPlayer

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py path/to/behavior.xar")
        sys.exit(1)

    xar_path = sys.argv[1]
    app = qi.Application(["XarPlayer", "--qi-url=tcp://127.0.0.1:9559"])
    app.start()
    session = app.session

    player = XarPlayer(session, xar_path)
    player.run()

if __name__ == "__main__":
    main()
