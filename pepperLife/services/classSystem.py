# -*- coding: utf-8 -*-
# classSystem.py — Couleurs pour la console et gestion de version
import os
import io
import sys
import subprocess
import logging
import json
import ast
import xml.etree.ElementTree as ET


os.environ.pop("OPENAI_LOG", None)  # évite que l'ENV force DEBUG

for name in ("openai", "openai._base_client", "httpx", "httpcore"):
    lg = logging.getLogger(name)
    lg.setLevel(logging.WARNING)   # ou logging.ERROR si tu veux couper encore plus
    lg.propagate = False

class bcolors:
    HEADER = '\x1b[95m'
    OKBLUE = '\x1b[94m'
    OKCYAN = '\x1b[96m'
    OKGREEN = '\x1b[92m'
    WARNING = '\x1b[93m'
    FAIL = '\x1b[91m'
    ENDC = '\x1b[0m'
    BOLD = '\x1b[1m'
    UNDERLINE = '\x1b[4m'

class version(object):
    _here = os.path.dirname(os.path.abspath(__file__))
    version_path = os.path.join(os.path.dirname(_here), "version")
    _cached_pkg_version = None

    @classmethod
    def get(cls, default=u"dev"):
        pkg_version = cls._get_package_version()
        if pkg_version:
            return pkg_version
        try:
            if os.path.isfile(cls.version_path):
                with io.open(cls.version_path, "r", encoding="utf-8") as f:
                    return f.read().strip() or default
        except Exception:
            pass
        return default

    @classmethod
    def _get_package_version(cls):
        if cls._cached_pkg_version:
            return cls._cached_pkg_version
        try:
            output = subprocess.check_output(
                ['qicli', 'call', 'PackageManager.getPackage', 'pepperlife'],
                stderr=subprocess.STDOUT
            )
            if isinstance(output, bytes):
                text = output.decode('utf-8', 'ignore')
            else:
                text = output
            text = (text or '').strip()
            if not text:
                return None
            try:
                data = ast.literal_eval(text)
            except Exception:
                return None
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, list) and len(entry) >= 2 and entry[0] == 'version':
                        value = entry[1]
                        if isinstance(value, (str, bytes)):
                            cls._cached_pkg_version = value.decode('utf-8', 'ignore') if isinstance(value, bytes) else value
                        else:
                            cls._cached_pkg_version = str(value)
                        if cls._cached_pkg_version:
                            cls._cached_pkg_version = cls._cached_pkg_version.strip()
                        return cls._cached_pkg_version or None
        except Exception:
            return None
        return None

    @classmethod
    def is_python3_nao_installed(cls):
        """Vérifie si le lanceur python3 de NAOqi est présent."""
        runner_path = '/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh'
        return os.path.exists(runner_path)


NAOQI_VERSION_FILE = '/opt/aldebaran/etc/version/naoqi_version'


def read_naoqi_version_from_file(path=NAOQI_VERSION_FILE):
    """Retourne la version NAOqi en lisant le fichier système dédié."""
    try:
        with io.open(path, 'r', encoding='utf-8') as fh:
            data = fh.read().strip()
            return data or None
    except Exception:
        return None


class RobotIdentityManager(object):
    """Centralise la détection et la gestion de l'identité robot."""

    def __init__(self, svc_getter, logger=None):
        self._svc_getter = svc_getter
        self._logger = logger or (lambda *a, **k: None)
        self._identity = None
        self._custom_name = None
        self._last_identity_log = (None, None)
        self._robot_config = None

    def set_identity(self, identity):
        if isinstance(identity, dict):
            self._identity = self._augment_identity_with_name(dict(identity))
        elif identity:
            self._identity = self._augment_identity_with_name({'type': str(identity).strip().lower()})
        else:
            self._identity = self._augment_identity_with_name({'type': 'pepper'})
        return self._identity

    def get_identity(self):
        if self._identity:
            return self._identity
        detected = self._detect_robot_identity()
        if detected:
            self._identity = self._augment_identity_with_name(detected)
        return self._identity or {'type': 'pepper'}

    def refresh_identity(self):
        """Force une redétection (utilisé quand l'état robot peut changer)."""
        self._identity = None
        self._robot_config = None
        self._custom_name = None
        return self.get_identity()

    def get_robot_type(self):
        identity = self.get_identity()
        value = identity.get('type')
        if isinstance(value, str):
            lowered = value.strip().lower()
            return lowered or 'pepper'
        if value is None:
            return 'pepper'
        return str(value).strip().lower() or 'pepper'

    def get_robot_name(self):
        identity = self.get_identity()
        name = identity.get('name') if isinstance(identity, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()
        resolved = self._get_robot_name_from_memory()
        if resolved:
            if isinstance(identity, dict):
                identity['name'] = resolved
            return resolved
        return None

    # ------------------------------------------------------------------ Internals
    def _svc(self, name):
        getter = self._svc_getter
        if not callable(getter):
            return None
        try:
            return getter(name)
        except Exception:
            return None

    def _load_robot_config(self, force=False):
        if self._robot_config is not None and not force:
            return self._robot_config
        try:
            output = subprocess.check_output(
                ['qicli', 'call', 'ALRobotModel.getConfig'],
                stderr=subprocess.STDOUT
            )
            if isinstance(output, bytes):
                text = output.decode('utf-8', 'ignore')
            else:
                text = output
            text = (text or '').strip()
            if not text:
                self._robot_config = None
                return None
            root = ET.fromstring(text)
        except Exception as exc:
            self._robot_config = None
            try:
                self._logger("[Identity] Lecture de la config robot impossible: %s" % exc, level='debug')
            except Exception:
                pass
            return None
        config = {}
        for pref in root.iter():
            tag = pref.tag.split('}', 1)[-1] if '}' in pref.tag else pref.tag
            if tag != 'Preference':
                continue
            memory_name = pref.attrib.get('memoryName') or pref.attrib.get('name')
            value = pref.attrib.get('value')
            if not memory_name or value is None:
                continue
            text_value = value.strip() if isinstance(value, str) else str(value).strip()
            if text_value:
                config[memory_name] = text_value
        self._robot_config = config or None
        return self._robot_config

    def _get_config_entry(self, keys):
        config = self._load_robot_config()
        if not config:
            return (None, None)
        for key in keys:
            value = config.get(key)
            if value is None:
                continue
            text_value = value.strip() if isinstance(value, str) else str(value).strip()
            if text_value:
                return (key, text_value)
        return (None, None)

    def _get_config_value(self, keys):
        _, value = self._get_config_entry(keys)
        return value

    def _detect_robot_identity(self):
        cfg_key, cfg_value = self._get_config_entry((
            "RobotConfig/Body/Type",
            "RobotConfig/Body/Type/Value",
            "RobotConfig/Head/Type",
            "RobotConfig/Head/Type/Value",
            "RobotConfig/Body/Version",
            "RobotConfig/Head/Version",
        ))
        if cfg_value:
            normalized = self._normalize_robot_type(cfg_value)
            if normalized:
                return {'type': normalized, 'raw': cfg_value, 'source': cfg_key or 'ALRobotModel.getConfig'}
        almem = self._svc('ALMemory')
        if not almem:
            return None
        keys_to_try = (
            "RobotConfig/Body/Type",
            "RobotConfig/Body/Type/Value",
            "Device/DeviceList/Body/Type",
            "Device/DeviceList/Body/Type/Value",
            "Device/SubDeviceList/Body/Type/Value",
            "Body/Type",
            "Body/Type/Value",
        )
        for key in keys_to_try:
            try:
                value = almem.getData(key)
            except Exception:
                continue
            normalized = self._normalize_robot_type(value)
            if normalized:
                return {'type': normalized, 'raw': value, 'source': key}
        return None

    def _get_robot_name_from_memory(self):
        if self._custom_name:
            return self._custom_name
        env_name = os.environ.get('PEPPER_ROBOT_NAME')
        if isinstance(env_name, str) and env_name.strip():
            self._custom_name = env_name.strip()
            return self._custom_name
        try:
            al_system = self._svc('ALSystem')
            if al_system:
                for attr in ('robotName', 'getRobotName', 'deviceName'):
                    fn = getattr(al_system, attr, None)
                    if callable(fn):
                        value = fn()
                        if isinstance(value, str) and value.strip():
                            self._custom_name = value.strip()
                            return self._custom_name
        except Exception:
            pass
        name_keys = (
            "RobotConfig/Body/CustomName",
            "RobotConfig/Head/CustomName",
            "RobotConfig/Body/CustomName/Value",
            "RobotConfig/Head/CustomName/Value",
            "RobotConfig/Robot/CustomName",
            "RobotConfig/Robot/CustomName/Value",
            "RobotConfig/Robot/Name",
            "RobotConfig/Robot/Name/Value",
            "Device/SubDeviceList/Body/CustomName/Value",
            "Device/SubDeviceList/Head/CustomName/Value",
            "Device/SubDeviceList/Body/DeviceName/Value",
            "Device/SubDeviceList/Head/DeviceName/Value",
            "Device/DeviceList/Body/Name",
            "Device/DeviceList/Head/Name",
            "ALTextToSpeech/CurrentVoice",
        )
        cfg_key, cfg_value = self._get_config_entry(name_keys)
        if cfg_value:
            self._custom_name = cfg_value
            return self._custom_name
        try:
            almem = self._svc('ALMemory')
            if almem:
                for key in name_keys:
                    try:
                        value = almem.getData(key)
                    except Exception:
                        continue
                    if isinstance(value, str) and value.strip():
                        self._custom_name = value.strip()
                        return self._custom_name
        except Exception:
            pass
        fallback_type_keys = (
            "RobotConfig/Body/Type",
            "RobotConfig/Body/Type/Value",
            "RobotConfig/Head/Type",
            "RobotConfig/Head/Type/Value",
        )
        fallback_type = self._get_config_value(fallback_type_keys)
        if not fallback_type:
            almem = self._svc('ALMemory')
            if almem:
                for key in fallback_type_keys:
                    try:
                        value = almem.getData(key)
                    except Exception:
                        continue
                    if value:
                        fallback_type = value
                        break
        if fallback_type:
            normalized = self._normalize_robot_type(fallback_type)
            self._custom_name = normalized or str(fallback_type).strip()
            return self._custom_name
        return None

    def _get_robot_serial(self):
        head_keys = (
            "RobotConfig/Head/FullHeadId",
            "RobotConfig/Head/HeadId",
            "RobotConfig/Head/HeadID",
            "RobotConfig/Head/HeadId/Value",
            "RobotConfig/Head/HeadID/Value",
            "Device/SubDeviceList/Head/HeadId/Value",
            "Device/SubDeviceList/Head/SerialNumber/Value",
            "Device/SubDeviceList/Head/Serial/Value",
            "Device/SubDeviceList/Head/HeadID/Value",
            "Device/SubDeviceList/Head/HeadId/Sensor/Value",
            "Device/SubDeviceList/Head/HeadId/Actuator/Value",
            "Device/SubDeviceList/Head/ID/Value",
            "Device/DeviceList/Head/ID/Value",
            "Head/ID",
            "Head/ID/Value"
        )
        cfg_key, cfg_value = self._get_config_entry(head_keys)
        if cfg_value:
            self._logger("[Choreo] Serial via RobotConfig key %s -> %s" % (cfg_key, cfg_value), level='debug')
            return cfg_value
        almem = self._svc('ALMemory')
        if not almem:
            return None
        for key in head_keys:
            try:
                value = almem.getData(key)
                if value:
                    serial = str(value)
                    self._logger("[Choreo] Serial via Head key %s -> %s" % (key, serial), level='debug')
                    return serial
            except Exception:
                continue
        try:
            config_keys = almem.getDataList("RobotConfig/")
            candidate_keys = [k for k in config_keys if 'head' in k.lower() and 'id' in k.lower()]
            if candidate_keys:
                values = almem.getListData(candidate_keys)
                for key, value in zip(candidate_keys, values):
                    if value:
                        serial = str(value)
                        self._logger("[Choreo] Serial via RobotConfig key %s -> %s" % (key, serial), level='debug')
                        return serial
        except Exception:
            pass
        return None

    def _augment_identity_with_name(self, identity):
        if not isinstance(identity, dict):
            return identity
        identity = dict(identity)
        if not identity.get('name'):
            name = self._get_robot_name_from_memory()
            if name:
                identity['name'] = name
        if not identity.get('serial'):
            serial = self._get_robot_serial()
            if serial:
                identity['serial'] = serial
        current = (identity.get('name'), identity.get('serial'))
        if current != self._last_identity_log:
            self._logger("[Choreo] Identité robot: name=%s serial=%s" % current, level='info')
            self._last_identity_log = current
        return identity

    @staticmethod
    def _normalize_robot_type(value):
        if value is None:
            return None
        try:
            text = value.strip()
        except AttributeError:
            text = str(value).strip()
        if not text:
            return None
        lowered = text.lower()
        if 'pepper' in lowered:
            return 'pepper'
        if 'nao' in lowered:
            return 'nao'
        if 'romeo' in lowered:
            return 'romeo'
        return lowered

# --- Prompt dynamique --------------------------------------------------

def build_system_prompt_in_memory(base_text, animation_families_list):
    """
    Prend un texte de base, une liste de familles d'animations,
    et renvoie (prompt, count).
    """
    if not base_text:
        base_text = "CATALOGUE DES ANIMATIONS DISPONIBLES (utilise ces clés telles quelles)\n{{CATALOGUE_AUTO}}"

    lines = animation_families_list or []
    catalogue = "\n".join(lines)

    if "{{CATALOGUE_AUTO}}" in base_text:
        prompt = base_text.replace("{{CATALOGUE_AUTO}}", catalogue)
    else:
        head = "CATALOGUE DES ANIMATIONS DISPONIBLES"
        if head in base_text:
            before, _, _ = base_text.partition(head)
            prompt = before + head + "\n" + catalogue
        else:
            prompt = base_text.rstrip() + "\n\n" + head + "\n" + catalogue

    return prompt, len(lines)


# --- Gestion de la configuration -----------------------------------------

import json
import traceback

def handle_exception(args):
    """
    Capture les exceptions non gérées dans n'importe quel thread et les logue.
    """
    # Le thread.excepthook a besoin d'une fonction qui accepte un seul argument
    # args est un objet contenant exc_type, exc_value, exc_traceback
    log_func = logging.getLogger().error
    log_func("ERREUR NON GÉRÉE DANS LE THREAD: {}".format(args.thread.name))
    
    # Formatage de la traceback pour l'afficher proprement
    exc_type, exc_value, exc_traceback = args.exc_type, args.exc_value, args.exc_traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    for line in tb_lines:
        log_func(line.strip())

def load_config(logger):
    """
    Charge la configuration depuis les fichiers, en fusionnant les valeurs par défaut
    et en créant le fichier utilisateur si nécessaire.
    Retourne le dictionnaire de configuration complet.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.expanduser('~/.config/pepperlife')
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    config_path = os.path.join(config_dir, 'config.json')
    default_config_path = os.path.join(os.path.dirname(script_dir), 'config.json.default')

    # Charger la configuration par défaut en premier, elle est toujours nécessaire
    try:
        with open(default_config_path, 'r', encoding='utf-8') as f:
            default_config = json.load(f)
    except Exception as e:
        logger("ERREUR CRITIQUE: Impossible de charger ou parser config.json.default: {}".format(e), level='error', color=bcolors.FAIL)
        sys.exit(1)

    if not os.path.exists(config_path):
        logger("Le fichier config.json n'existe pas, création à partir des valeurs par défaut...", level='warning', color=bcolors.WARNING)
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            # Utiliser directement la configuration par défaut puisqu'on vient de la créer
            user_config = default_config
        except Exception as e:
            logger("ERREUR CRITIQUE: Impossible de créer le fichier config.json: {}".format(e), level='error', color=bcolors.FAIL)
            sys.exit(1)
    else:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            logger("User config loaded: {}".format(json.dumps(user_config)), level='debug')
        except Exception as e:
            logger("ERREUR CRITIQUE: Impossible de charger ou parser config.json: {}".format(e), level='error', color=bcolors.FAIL)
            # On ne quitte pas, on tente de continuer avec la config par défaut
            user_config = default_config

    updated = False
    for key, value in default_config.items():
        if key not in user_config:
            logger("Clé manquante '{}' dans config.json, ajout...".format(key), level='warning', color=bcolors.WARNING)
            user_config[key] = value
            updated = True
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_key not in user_config[key]:
                    logger("Clé manquante '{}.{}' dans config.json, ajout...".format(key, sub_key), level='warning', color=bcolors.WARNING)
                    user_config[key][sub_key] = sub_value
                    updated = True

    if updated:
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(user_config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger("Erreur lors de la mise à jour de config.json: {}".format(e), level='warning')

    return user_config
