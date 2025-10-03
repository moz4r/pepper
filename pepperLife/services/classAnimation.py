# -*- coding: utf-8 -*-
# services/classAnimation.py
# NAOqi 2.7 / 2.9 — normalisation ^start(...), comptage et résolution des animations.
# 2.9 : on scanne UNIQUEMENT ~/.local/share/PackageManager/apps/animations/**.qianim
#       (entrées relatives au dossier 'animations/') et on ÉMET toujours 'animation/...*.qianim'
# 2.7 : on utilise les clés NAOqi 'animations/...'.

import re
import random
from pathlib import Path

try:
    from services.classSystem import bcolors
except Exception:
    class bcolors:
        WARNING = '\033[93m'
        ENDC = '\033[0m'

class Animation(object):
    RE_START = re.compile(r'^\s*\^start\(([^)]+)\)\s*', re.IGNORECASE)
    RE_SUFFIX_NUM = re.compile(r'_(\d+)$')

    def __init__(self, session, logger, robot_version=None):
        self.s = session
        self.log = logger
        self.robot_version = robot_version or self._probe_version()
        self.is_29 = self._is_29(self.robot_version)

        # Inventaire
        self.installed_keys = set()      # 2.7 : "animations/Stand/.../Name_N"
        self.installed_qianim = set()    # 2.9 : "Stand/.../Name_01.qianim" (relatifs à 'animations/')
        self.by_prefix_keys = {}         # 2.7 : "animations/.../Name_" -> [...]
        self.by_prefix_qianim = {}       # 2.9 : "Stand/.../Name_" -> [...]
        self.animation_families = {}     # "animations/.../Name" -> [...]

        self.last_resolved = None
        self.refresh()  # log jaune “X animations chargées”

    # ------------- Version -------------
    def _probe_version(self):
        try:
            sys = self.s.service("ALSystem")
            return sys.systemVersion()
        except Exception:
            return "0.0.0.0"

    @staticmethod
    def _is_29(ver_str):
        nums = [int(x) for x in re.findall(r"\d+", ver_str)[:2]] or [0, 0]
        return tuple(nums) >= (2, 9)

    # ------------- Scan / Refresh -------------
    def refresh(self):
        """Recharge l'inventaire et log EN JAUNE 'X animations chargées' une seule fois ici."""
        # 2.7 — clés NAOqi
        keys = []
        try:
            ap = self.s.service("ALAnimationPlayer")
            keys = ap.getInstalledAnimations() or []
        except Exception:
            try:
                bm = self.s.service("ALBehaviorManager")
                keys = [a for a in bm.getInstalledBehaviors() if a.startswith("animations/")]
            except Exception:
                keys = []
        self.installed_keys = set(keys)
        self.by_prefix_keys.clear()
        for a in self.installed_keys:
            fam = self.RE_SUFFIX_NUM.sub("_", a)
            self.by_prefix_keys.setdefault(fam, []).append(a)

        # 2.9 — fichiers .qianim sous ~/.local/share/PackageManager/apps/animations/
        self.installed_qianim.clear()
        self.by_prefix_qianim.clear()
        if self.is_29:
            base = Path.home() / ".local/share/PackageManager/apps/animations"
            if base.is_dir():
                for p in base.rglob("*.qianim"):
                    rel = p.relative_to(base).as_posix()  # ex: Stand/Gestures/Hey_1/Hey_1.qianim
                    self.installed_qianim.add(rel)
                    noext = rel[:-7]  # retire .qianim
                    fam = self.RE_SUFFIX_NUM.sub("_", noext)  # Name_03 -> Name_
                    self.by_prefix_qianim.setdefault(fam, []).append(rel)

        # Familles unifiées
        self.animation_families.clear()
        prefix_map = self.by_prefix_qianim if self.is_29 else self.by_prefix_keys
        for fam_underscore, anims in prefix_map.items():
            # Clé propre: 'animations/Stand/Gestures/Hey_' -> 'animations/Stand/Gestures/Hey'
            clean_fam = fam_underscore.rstrip('_')
            self.animation_families[clean_fam] = anims

        # Log (une seule fois ici)
        count = len(self.installed_qianim) if self.is_29 else len(self.installed_keys)
        fam_count = len(self.animation_families)
        log_msg = f"{count} animations chargées, compressées en {fam_count} familles pour le prompt."
        try:
            self.log(log_msg, level='info', color=bcolors.WARNING)
        except TypeError:
            self.log(log_msg, level='info')

    # ------------- Helpers normalisation -------------
    @staticmethod
    def _strip_dot_slash(k):
        return k[2:] if k.startswith("./") else k

    @staticmethod
    def _ensure_anim27_prefix(k):
        # tolère 'Gestures/Hey_1' -> 'animations/Stand/Gestures/Hey_1'
        k = k.strip().lstrip("/")
        return k if k.startswith("animations/") else ("animations/Stand/" + k)

    @staticmethod
    def _to_qianim_relative(k):
        """
        2.9 : chemin RELATIF à 'animations/'.
        - supprime './' devant
        - supprime 'animations/' ou 'animation/' si présent
        """
        k = k.strip()
        k = k[2:] if k.startswith("./") else k
        if k.startswith("animations/"):
            k = k.split("animations/", 1)[1]
        elif k.startswith("animation/"):
            k = k.split("animation/", 1)[1]
        return k

    def _resolve_family_first_qianim(self, family_noext):
        fam = family_noext if family_noext.endswith("_") else (family_noext + "_")
        cands = self.by_prefix_qianim.get(fam, [])
        if cands:
            return cands[0]
        # fallback: premier qui commence par fam
        for q in sorted(self.installed_qianim):
            if q.startswith(fam):
                return q
        return None

    def _resolve_family_first_key(self, family_key):
        fam = family_key if family_key.endswith("_") else (family_key + "_")
        cands = self.by_prefix_keys.get(fam, [])
        if cands:
            return cands[0]
        for k in sorted(self.installed_keys):
            if k.startswith(fam):
                return k
        return None

    # ------------- Émission 2.9 -------------
    def _emit29(self, rel_path):
        """
        Force le préfixe 'animations/' (pluriel) pour 2.9.
        Ajoute '.qianim' si absent.
        """
        rp = rel_path
        if not rp.endswith(".qianim"):
            cand = rp + ".qianim"
            rp = cand if cand in self.installed_qianim else (rp + ".qianim")
        return rp if rp.startswith("animations/") else ("animations/" + rp)

    # ------------- API publique -------------
    def get_animation_families(self):
        """Retourne une liste triée des noms de familles d'animations."""
        return sorted(self.animation_families.keys())

    def get_installed_animations(self):
        """Retourne une liste triée des animations installées (clés ou .qianim)."""
        return sorted(list(self.installed_qianim if self.is_29 else self.installed_keys))

    def health_check(self):
        """
        Ne loggue pas le compteur (déjà loggué au refresh).
        Retourne True si au moins une anim trouvée pour la version courante.
        """
        return (len(self.installed_qianim) > 0) if self.is_29 else (len(self.installed_keys) > 0)

    def normalize_text(self, text, intent=None):
        """
        Si ^start(...) est présent, réécrit le début :
        - Gère les familles d'animations (ex: 'Hey') en choisissant une anim au hasard.
        - 2.9 : accepte entrée avec/ sans 'animation(s)/', et émet toujours 'animation/...*.qianim'
        - 2.7 : accepte 'animations/...'
        """
        t = text or ""
        m = self.RE_START.match(t)
        if not m:
            return t

        raw = (m.group(1) or "").strip()
        chosen = None

        # ----- 2.9 (qianim) -----
        if self.is_29:
            key_rel = self._to_qianim_relative(raw)
            # Essai 1: La clé est une famille connue ?
            # (ex: Stand/Gestures/Hey sans _ et sans .qianim)
            family_anims = self.animation_families.get(key_rel)
            if family_anims:
                chosen = random.choice(family_anims)
                self.log(f"[ANIM] Famille '{raw}' -> Choix aléatoire: {chosen}", level='info')
            else:
                # Essai 2: C'est un chemin exact vers un .qianim ?
                if key_rel in self.installed_qianim:
                    chosen = key_rel
                # Essai 3: C'est un chemin sans .qianim ?
                elif f"{key_rel}.qianim" in self.installed_qianim:
                    chosen = f"{key_rel}.qianim"

            if not chosen:
                self.log(f"[ANIM] Animation ou famille inconnue (2.9): '{raw}'", level='warning')
                chosen = key_rel # On tente quand même de l'envoyer

            emit = self._emit29(chosen)
            self.last_resolved = emit
            head = f"^start({emit}) "
            return self.RE_START.sub(head, t, count=1)

        # ----- 2.7 (clés NAOqi) -----
        else:
            key = self._ensure_anim27_prefix(self._strip_dot_slash(raw))
            # Essai 1: La clé est une famille connue ?
            # (ex: animations/Stand/Gestures/Hey)
            family_anims = self.animation_families.get(key)
            if family_anims:
                chosen = random.choice(family_anims)
                self.log(f"[ANIM] Famille '{raw}' -> Choix aléatoire: {chosen}", level='info')
            # Essai 2: C'est une clé exacte connue ?
            elif key in self.installed_keys:
                chosen = key

            if not chosen:
                self.log(f"[ANIM] Animation ou famille inconnue (2.7): '{raw}'", level='warning')
                chosen = key # On tente quand même

            self.last_resolved = chosen
            head = f"^start({chosen}) "
            return self.RE_START.sub(head, t, count=1)
