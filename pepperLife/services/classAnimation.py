# -*- coding: utf-8 -*-
# services/classAnimation.py
# NAOqi 2.7 / 2.9 — normalisation ^start(...), comptage et résolution des animations.
# 2.9 : on scanne UNIQUEMENT ~/.local/share/PackageManager/apps/animations/**.qianim
#       (entrées relatives au dossier 'animations/') et on ÉMET toujours 'animation/...*.qianim'
# 2.7 : on utilise les clés NAOqi 'animations/...'.

import re
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

        # Log jaune (une seule fois ici)
        count = len(self.installed_qianim) if self.is_29 else len(self.installed_keys)
        try:
            self.log(f"{count} animations chargées", level='info', color=bcolors.WARNING)
        except TypeError:
            self.log(f"{count} animations chargées", level='info')

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
    def health_check(self):
        """
        Ne loggue pas le compteur (déjà loggué au refresh).
        Retourne True si au moins une anim trouvée pour la version courante.
        """
        return (len(self.installed_qianim) > 0) if self.is_29 else (len(self.installed_keys) > 0)

    def normalize_text(self, text, intent=None):
        """
        Si ^start(...) est présent, réécrit le début :
        - 2.9 : accepte entrée avec/ sans 'animation(s)/', et émet toujours 'animation/...*.qianim'
        - 2.7 : accepte 'animations/...'
        Ajoute ^wait(KEY) juste après ^start(KEY).
        """
        t = text or ""
        m = self.RE_START.match(t)
        if not m:
            return t

        raw = (m.group(1) or "").strip()

        # ----- 2.9 -----
        if self.is_29:
            key_rel = self._to_qianim_relative(raw)  # relatif à 'animations/'
            chosen = None

            # exact (avec extension)
            if key_rel in self.installed_qianim:
                chosen = key_rel
            else:
                # famille si pas de suffixe numérique
                base_noext = key_rel[:-7] if key_rel.endswith(".qianim") else key_rel
                if not self.RE_SUFFIX_NUM.search(base_noext):
                    fam = self._resolve_family_first_qianim(base_noext)
                    if fam:
                        self.log("[ANIM] ^start(%s) -> %s" % (raw, fam), level='info')
                        chosen = fam

            if not chosen:
                chosen = key_rel

            emit = self._emit29(chosen)
            self.last_resolved = emit
            head = "^start(%s)^wait(%s) " % (emit, emit)
            return self.RE_START.sub(head, t, count=1)

        # ----- 2.7 -----
        key = self._ensure_anim27_prefix(self._strip_dot_slash(raw))
        if key in self.installed_keys:
            self.last_resolved = key
            head = "^start(%s)^wait(%s) " % (key, key)
            return self.RE_START.sub(head, t, count=1)

        fam = self.RE_SUFFIX_NUM.sub("_", key)
        resolved = self._resolve_family_first_key(fam)
        if resolved:
            self.log("[ANIM] ^start(%s) -> %s" % (raw, resolved), level='info')
            self.last_resolved = resolved
            head = "^start(%s)^wait(%s) " % (resolved, resolved)
            return self.RE_START.sub(head, t, count=1)

        self.log("[ANIM] clé inconnue: %s" % key, level='warning')
        self.last_resolved = key
        head = "^start(%s)^wait(%s) " % (key, key)
        return self.RE_START.sub(head, t, count=1)
