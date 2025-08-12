#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Émulateur NAOqi pour Choregraphe (Python 2.7) — version étendue + SNIFFER DEBUG
Port par défaut : 9999
Services exposés : ALTextToSpeech, ALMemory, ALSystem, ALLauncher, ALServiceManager,
                   ALBattery, ALRobotPosture, ALPreferences, ALRobotModel, ALMotion

Objectif : connexion fiable + logs détaillés, avec des services-clés simulés
(batterie, posture, préférences, modèle, motion) pour réduire les warnings.
"""

import qi
import sys
import time
import threading
import json
from datetime import datetime

# -------------------- DEBUG / SNIFFER --------------------
DEBUG = True

def _short(v, maxlen=200):
    try:
        s = json.dumps(v, default=str, ensure_ascii=False)
    except Exception:
        try:
            s = repr(v)
        except Exception:
            s = '<unrepr>'
    if len(s) > maxlen:
        s = s[:maxlen] + '…'
    return s

def log(service, msg):
    if not DEBUG:
        return
    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    try:
        sys.stdout.write('[{}][{}] {}\n'.format(ts, service, msg))
        sys.stdout.flush()
    except Exception:
        pass

def sniff_calls(service_name):
    """Décorateur : log les appels (args/retours) de méthodes d'API."""
    def deco(fn):
        def wrapper(*args, **kwargs):
            try:
                args_fmt = ', '.join(_short(a) for a in args[1:])  # skip self
                if kwargs:
                    args_fmt += (', ' if args_fmt else '') + ', '.join('{}={}'.format(k, _short(v)) for k, v in kwargs.items())
                log(service_name, '{}({})'.format(fn.__name__, args_fmt))
            except Exception:
                pass
            try:
                out = fn(*args, **kwargs)
                try:
                    log(service_name, '{} -> {}'.format(fn.__name__, _short(out)))
                except Exception:
                    pass
                return out
            except Exception as e:
                log(service_name, '{} !! {}: {}'.format(fn.__name__, type(e).__name__, e))
                raise
        try:
            wrapper.__name__ = fn.__name__
        except Exception:
            pass
        return wrapper
    return deco

# -------------------- Fake TTS --------------------
class FakeTTS(object):
    @sniff_calls('ALTextToSpeech')
    def say(self, text):
        return 'ok'

# -------------------- Fake ALMemory --------------------
class FakeMemory(object):
    def __init__(self):
        self.data = {'NAOqiReady': True}
        self.lock = threading.Lock()
        self._version = '2.8.8.0'
        self._subs_events = {}  # event -> { module: method }
        self._subs_micro = {}   # event -> { module: (cbModule, cbMethod) }
        log('ALMemory', 'init (version {})'.format(self._version))

    @sniff_calls('ALMemory')
    def version(self):
        return self._version

    @sniff_calls('ALMemory')
    def insertData(self, key, value):
        with self.lock:
            self.data[key] = value
        return True

    @sniff_calls('ALMemory')
    def getData(self, key):
        if key == 'NAOqiReady':
            return True
        with self.lock:
            return self.data.get(key, None)

    @sniff_calls('ALMemory')
    def getEventList(self):
        return sorted(self._subs_events.keys())

    @sniff_calls('ALMemory')
    def getMicroEventList(self):
        return sorted(self._subs_micro.keys())

    @sniff_calls('ALMemory')
    def getDataList(self, prefix=''):
        with self.lock:
            return [k for k in self.data.keys() if k.startswith(prefix)]

    @sniff_calls('ALMemory')
    def subscriber(self, eventName):
        # Retourne un objet avec un signal AnyValue sous forme (m)
        class _FakeSubscriber(object):
            def __init__(self):
                try:
                    self.signal = qi.Signal('(m)')
                except Exception:
                    try:
                        self.signal = qi.Signal('m')
                    except Exception:
                        try:
                            self.signal = qi.Signal()
                        except Exception:
                            self.signal = None
        return _FakeSubscriber()

    @sniff_calls('ALMemory')
    def raiseMicroEvent(self, eventName, value):
        return self.raiseEvent(eventName, value)

    @sniff_calls('ALMemory')
    def raiseEvent(self, key, value):
        with self.lock:
            self.data[key] = value
            subs_e = dict(self._subs_events.get(key, {}))
            subs_m = dict(self._subs_micro.get(key, {}))
        for module, method in subs_e.items():
            log('ALMemory', '(notify event) {}.{}({}) for {}'.format(module, method, _short(value), key))
        for module, cb in subs_m.items():
            cb_mod, cb_meth = cb
            log('ALMemory', '(notify micro) {}.{} via {} for {}'.format(cb_mod, cb_meth, module, key))
        return True

    @sniff_calls('ALMemory')
    def subscribeToEvent(self, eventName, moduleName, methodName):
        self._subs_events.setdefault(eventName, {})[moduleName] = methodName
        return True

    @sniff_calls('ALMemory')
    def unsubscribeToEvent(self, eventName, moduleName):
        self._subs_events.get(eventName, {}).pop(moduleName, None)
        return True

    @sniff_calls('ALMemory')
    def subscribeToMicroEvent(self, eventName, moduleName, callbackModule, callbackMethod):
        self._subs_micro.setdefault(eventName, {})[moduleName] = (callbackModule, callbackMethod)
        return True

    @sniff_calls('ALMemory')
    def unsubscribeToMicroEvent(self, eventName, moduleName):
        self._subs_micro.get(eventName, {}).pop(moduleName, None)
        return True

# -------------------- Fake ALSystem --------------------
class FakeSystem(object):
    def __init__(self):
        self.version_str = '2.9.0.0-fake'
        self.robot_name = 'PepperFake'

    @sniff_calls('ALSystem')
    def systemVersion(self):
        return self.version_str

    @sniff_calls('ALSystem')
    def robotName(self):
        return self.robot_name

    @sniff_calls('ALSystem')
    def robotType(self):
        return 'Pepper'

# -------------------- Fake ALLauncher --------------------
class FakeALLauncher(object):
    @sniff_calls('ALLauncher')
    def launchExecutable(self, path, args=None):
        return True
    @sniff_calls('ALLauncher')
    def stop(self, name):
        return True
    @sniff_calls('ALLauncher')
    def isRunning(self, name):
        return False

# -------------------- Fake ALServiceManager --------------------
class FakeALServiceManager(object):
    def __init__(self, services):
        # Signaux (si): (serviceName, pid)
        try:
            self.serviceStarted = qi.Signal('(si)')
            self.serviceStopped = qi.Signal('(si)')
        except Exception:
            try:
                self.serviceStarted = qi.Signal((str, int))
                self.serviceStopped = qi.Signal((str, int))
            except Exception:
                self.serviceStarted = qi.Signal()
                self.serviceStopped = qi.Signal()
        self._services = list(services)
        log('ALServiceManager', 'init services={}'.format(self._services))

    @sniff_calls('ALServiceManager')
    def services(self):
        # Laisser vide pour éviter la conversion ServiceProcessInfo tant qu’on ne mappe pas la struct
        return []

    @sniff_calls('ALServiceManager')
    def getServices(self):
        return []

    @sniff_calls('ALServiceManager')
    def getServicesProcessInfo(self):
        return []

    @sniff_calls('ALServiceManager')
    def serviceExists(self, name):
        return name in self._services

    @sniff_calls('ALServiceManager')
    def add(self, name):
        if name not in self._services:
            self._services.append(name)
            try:
                self.serviceStarted.emit(name, 0)
            except Exception:
                try:
                    self.serviceStarted.emit((name, 0))
                except Exception:
                    pass
        return True

    @sniff_calls('ALServiceManager')
    def remove(self, name):
        if name in self._services:
            self._services.remove(name)
            try:
                self.serviceStopped.emit(name, 0)
            except Exception:
                try:
                    self.serviceStopped.emit((name, 0))
                except Exception:
                    pass
        return True

# -------------------- Fake ALBattery --------------------
class FakeALBattery(object):
    def __init__(self, memory):
        self._charge = 87  # %
        self._temp = 34.2  # °C
        self._plugged = True
        self._mem = memory
        # clés ALMemory usuelles
        self._mem.insertData('Device/SubDeviceList/Battery/Charge/Sensor/Value', self._charge)
        self._mem.insertData('BatteryCharge/Charge', self._charge)
        self._mem.insertData('BatteryCharge/Plugged', int(self._plugged))
        log('ALBattery', 'init charge={} temp={} plugged={}'.format(self._charge, self._temp, self._plugged))

    @sniff_calls('ALBattery')
    def getBatteryCharge(self):
        return int(self._charge)

    @sniff_calls('ALBattery')
    def getBatteryTemperature(self):
        return float(self._temp)

    @sniff_calls('ALBattery')
    def isCharging(self):
        return bool(self._plugged)

    def _tick(self):
        if not self._plugged and self._charge > 5:
            self._charge -= 1
        elif self._plugged and self._charge < 100:
            self._charge += 1
        self._mem.insertData('BatteryCharge/Charge', int(self._charge))
        try:
            self._mem.raiseEvent('BatteryChargeChanged', int(self._charge))
        except Exception:
            pass

# -------------------- Fake ALRobotPosture --------------------
class FakeALRobotPosture(object):
    def __init__(self, memory):
        self._mem = memory
        self._postures = ['Stand', 'Crouch', 'Sit', 'SitRelax']
        self._current = 'Stand'
        self._family = 'Standing'
        self._mem.insertData('RobotPosture/Current', self._current)
        self._mem.insertData('RobotPosture/Family', self._family)
        log('ALRobotPosture', 'init posture={} family={}'.format(self._current, self._family))

    @sniff_calls('ALRobotPosture')
    def goToPosture(self, name, speed):
        if name not in self._postures:
            raise RuntimeError('Unknown posture: %s' % name)
        self._current = name
        self._family = 'Sitting' if name.startswith('Sit') else ('Crouching' if name=='Crouch' else 'Standing')
        self._mem.insertData('RobotPosture/Current', self._current)
        self._mem.insertData('RobotPosture/Family', self._family)
        try:
            self._mem.raiseEvent('ALRobotPosture/Changed', self._current)
        except Exception:
            pass
        try:
            self._mem.raiseEvent('PostureFamilyChanged', self._family)
        except Exception:
            pass
        return True

    @sniff_calls('ALRobotPosture')
    def getPosture(self):
        return self._current

    @sniff_calls('ALRobotPosture')
    def getPostureFamily(self):
        return self._family

    @sniff_calls('ALRobotPosture')
    def getPostureList(self):
        return list(self._postures)

# -------------------- Fake ALPreferences --------------------
class FakeALPreferences(object):
    def __init__(self):
        self._store = {
            'Network': {'WifiEnabled': True, 'Hostname': 'pepperfakedev', 'IP': '192.168.1.184'},
            'System':  {'Locale': 'fr_FR', 'Timezone': 'Europe/Paris'}
        }
        log('ALPreferences', 'init with domains={}'.format(self._store.keys()))

    @sniff_calls('ALPreferences')
    def getDomainList(self):
        return list(self._store.keys())

    @sniff_calls('ALPreferences')
    def getNames(self, domain):
        return list(self._store.get(domain, {}).keys())

    @sniff_calls('ALPreferences')
    def getValue(self, domain, name):
        return self._store.get(domain, {}).get(name, None)

    @sniff_calls('ALPreferences')
    def setValue(self, domain, name, value):
        self._store.setdefault(domain, {})[name] = value
        return True

    @sniff_calls('ALPreferences')
    def saveToDisk(self):
        return True

# -------------------- Fake ALRobotModel --------------------
class FakeALRobotModel(object):
    def __init__(self):
        self._type = 'Pepper'
        self._version = '2.9.0'
        log('ALRobotModel', 'init type={} version={}'.format(self._type, self._version))

    @sniff_calls('ALRobotModel')
    def getType(self):
        return self._type

    @sniff_calls('ALRobotModel')
    def getVersion(self):
        return self._version

    @sniff_calls('ALRobotModel')
    def getConfig(self):
        # Choregraphe attend ici un std::string → on renvoie une chaîne JSON
        cfg = {
            'type': self._type,
            'version': self._version,
            'joints': [],
            'actuators': [],
            'sensors': []
        }
        try:
            return json.dumps(cfg)
        except Exception:
            return '{}'
        return json.dumps(cfg)

# -------------------- Fake ALMotion --------------------
class FakeALMotion(object):
    def __init__(self, memory):
        self._mem = memory
        self._stopped = True
        # garder un petit état d’angles par nom
        self._angles = {}
        log('ALMotion', 'init ready')

    @sniff_calls('ALMotion')
    def moveTo(self, x, y, theta):
        # simple no-op avec délais simulé
        self._stopped = False
        try:
            self._mem.raiseEvent('ALMotion/MoveStarted', [x, y, theta])
        except Exception:
            pass
        time.sleep(0.05)
        self._stopped = True
        try:
            self._mem.raiseEvent('ALMotion/MoveDone', True)
        except Exception:
            pass
        return True

    @sniff_calls('ALMotion')
    def stopMove(self):
        self._stopped = True
        try:
            self._mem.raiseEvent('ALMotion/MoveStopped', True)
        except Exception:
            pass
        return True

    @sniff_calls('ALMotion')
    def setAngles(self, names, angles, speed):
        # accepte string ou liste
        if isinstance(names, basestring):
            names = [names]
        if isinstance(angles, (int, float)):
            angles = [float(angles)]
        for n, a in zip(names, angles):
            self._angles[n] = float(a)
        try:
            self._mem.raiseEvent('ALMotion/AnglesChanged', dict(self._angles))
        except Exception:
            pass
        return True

    @sniff_calls('ALMotion')
    def getAngles(self, names, useSensors):
        if isinstance(names, basestring):
            names = [names]
        return [float(self._angles.get(n, 0.0)) for n in names]

# -------------------- serveur --------------------

def main():
    try:
        session = qi.Session()
        session.listenStandalone('tcp://0.0.0.0:9999')
        log('CORE', 'listenStandalone ok on 0.0.0.0:9999')
    except RuntimeError as e:
        sys.stdout.write('[ERR] {}\n'.format(e))
        sys.exit(1)

    mem = FakeMemory()
    session.registerService('ALTextToSpeech', FakeTTS())
    session.registerService('ALMemory', mem)
    session.registerService('ALSystem', FakeSystem())
    session.registerService('ALLauncher', FakeALLauncher())

    battery = FakeALBattery(mem)
    session.registerService('ALBattery', battery)
    robot_posture = FakeALRobotPosture(mem)
    session.registerService('ALRobotPosture', robot_posture)
    prefs = FakeALPreferences()
    session.registerService('ALPreferences', prefs)
    robot_model = FakeALRobotModel()
    session.registerService('ALRobotModel', robot_model)
    motion = FakeALMotion(mem)
    session.registerService('ALMotion', motion)

    session.registerService('ALServiceManager', FakeALServiceManager([
        'ALTextToSpeech', 'ALMemory', 'ALSystem', 'ALLauncher',
        'ALServiceManager', 'ALBattery', 'ALRobotPosture',
        'ALPreferences', 'ALRobotModel', 'ALMotion'
    ]))

    # thread de tick batterie
    def battery_loop():
        while True:
            time.sleep(5)
            try:
                battery._tick()
            except Exception:
                pass

    t = threading.Thread(target=battery_loop)
    t.daemon = True
    t.start()

    log('CORE', 'registered services ok')
    log('CORE', 'ready: tcp://0.0.0.0:9999')

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log('CORE', 'stopping (KeyboardInterrupt)')

if __name__ == '__main__':
    main()
