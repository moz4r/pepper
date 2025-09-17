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
    version_path = os.path.join(os.path.dirname(_here), "version")

    @classmethod
    def get(cls, default=u"dev"):
        try:
            if os.path.isfile(cls.version_path):
                with io.open(cls.version_path, "r", encoding="utf-8") as f:
                    return f.read().strip() or default
        except Exception:
            pass
        return default

# --- Prompt dynamique (2.9 vs 2.7) -------------------------------------------
import re
from pathlib import Path

def _version_tuple(ver_str):
    try:
        return tuple(int(x) for x in re.findall(r"\d+", ver_str)[:4]) or (0,0,0,0)
    except Exception:
        return (0,0,0,0)

def _scan_qianim_for_29():
    base = Path.home() / ".local/share/PackageManager/apps/animations"
    if not base.is_dir():
        return []
    keys = []
    for p in base.rglob("*.qianim"):
        rel = p.relative_to(base).as_posix()  # => Stand/.../Name_01.qianim
        keys.append(rel)
    return sorted(set(keys))

def _scan_keys_for_27():
    """
    2.7 : renvoie des *clés* de répertoires avec préfixe animations/
    ex: animations/Stand/BodyTalk/Speaking/BodyTalk_13
    (un dossier est retenu s'il contient au moins un .qianim)
    """
    base = Path.home() / ".local/share/PackageManager/apps/animations"
    if not base.is_dir():
        return []
    out = set()
    for d in base.rglob("*"):
        if d.is_dir():
            try:
                if any(x.suffix == ".qianim" for x in d.iterdir()):
                    out.add(d.relative_to(Path.home() / ".local/share/PackageManager/apps/animation").as_posix())
            except Exception:
                pass
    return sorted(out)

def build_system_prompt_in_memory(base_text, robot_version_str):
    """
    Prend un texte de base, détecte 2.9 vs 2.7, scanne le bon format,
    et renvoie (prompt, count).
    """
    if not base_text:
        base_text = "CATALOGUE DES ANIMATIONS DISPONIBLES (utilise ces clés telles quelles)\n{{CATALOGUE_AUTO}}"

    is_29 = _version_tuple(robot_version_str) >= (2,9,0,0)
    lines = _scan_qianim_for_29() if is_29 else _scan_keys_for_27()
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
