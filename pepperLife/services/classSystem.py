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

    @classmethod
    def is_python3_nao_installed(cls):
        """Vérifie si le lanceur python3 de NAOqi est présent."""
        runner_path = '/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh'
        return os.path.exists(runner_path)

# --- Prompt dynamique --------------------------------------------------

def build_system_prompt_in_memory(base_text, animation_instance):
    """
    Prend un texte de base, récupère le catalogue d'animations via l'instance,
    et renvoie (prompt, count).
    """
    if not base_text:
        base_text = "CATALOGUE DES ANIMATIONS DISPONIBLES (utilise ces clés telles quelles)\n{{CATALOGUE_AUTO}}"

    lines = animation_instance.get_installed_animations() if animation_instance else []
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
