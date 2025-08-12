#!/usr/bin/env python
# -*- coding: utf-8 -*-

import qi
import sys
import time
import threading

# --- Fake TTS ---
class FakeTTS(object):
    def say(self, text):
        print("[Fake TTS] {}".format(text))
        return "ok"

# --- Fake ALMemory ---
class FakeMemory(object):
    def __init__(self):
        self.data = {"NAOqiReady": True}
        self.lock = threading.Lock()
        self._version = "0.1-fake"

    def version(self):
        print("[Fake ALMemory] version -> {}".format(self._version))
        return self._version

    def insertData(self, key, value):
        with self.lock:
            self.data[key] = value
        print("[Fake ALMemory] insertData {}={}".format(key, value))
        return True

    def getData(self, key):
        if key == "NAOqiReady":
            print("[Fake ALMemory] getData {} -> True".format(key))
            return True
        with self.lock:
            value = self.data.get(key, None)
        print("[Fake ALMemory] getData {} -> {}".format(key, value))
        return value

    def raiseEvent(self, key, value):
        with self.lock:
            self.data[key] = value
        print("[Fake ALMemory] raiseEvent {}={}".format(key, value))
        return True

# --- Fake ALSystem ---
class FakeSystem(object):
    def __init__(self):
        self.version_str = "2.9.0.0-fake"
        self.robot_name = "PepperFake"

    def systemVersion(self):
        print("[Fake ALSystem] systemVersion -> {}".format(self.version_str))
        return self.version_str

    def robotName(self):
        print("[Fake ALSystem] robotName -> {}".format(self.robot_name))
        return self.robot_name

    def robotType(self):
        print("[Fake ALSystem] robotType -> Pepper")
        return "Pepper"

def main():
    try:
        session = qi.Session()
        session.listenStandalone("tcp://0.0.0.0:9999")
        print("[INFO] Session listenStandalone OK sur port 9999")
    except RuntimeError as e:
        print("[ERR] Impossible de démarrer FakeNaoqi:", e)
        sys.exit(1)

    session.registerService("ALTextToSpeech", FakeTTS())
    session.registerService("ALMemory", FakeMemory())
    session.registerService("ALSystem", FakeSystem())

    print("[INFO] Fake NAOqi prêt sur tcp://0.0.0.0:9999")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Arrêt demandé par l'utilisateur.")

if __name__ == "__main__":
    main()
