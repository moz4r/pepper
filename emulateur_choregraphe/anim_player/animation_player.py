#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import glob
import xml.etree.ElementTree as ET
import qi

from xar_player import XarPlayer
from qianim_player import QianimPlayer

AUDIO_EXT = (".wav", ".mp3", ".ogg")

def _first_existing(*cands):
    for p in cands:
        if p and os.path.exists(p):
            return p
    return None

def _abspath(path):
    # robust absolute path
    return os.path.realpath(os.path.expanduser(path))

def resolve_input(arg_path):
    """
    Retourne (mode, path, audio_override). TOLÉRANT :
      - accepte fichier .qianim/.xar même si os.path.exists hésite (on laisse le player ouvrir le fichier)
      - si dossier : .qianim prioritaire, sinon .pml -> .xar
    """
    if not arg_path:
        raise RuntimeError("Aucun argument fourni.")
    arg_path = _abspath(arg_path)

    # Dossier
    if os.path.isdir(arg_path):
        qians = sorted(glob.glob(os.path.join(arg_path, "*.qianim")))
        if qians:
            return ("qianim", _abspath(qians[0]), None)

        pmls = sorted(glob.glob(os.path.join(arg_path, "*.pml")))
        if not pmls:
            raise RuntimeError("Aucun .qianim ni .pml trouvé dans: %s" % arg_path)
        pml = pmls[0]
        try:
            tree = ET.parse(pml)
            root = tree.getroot()
            xar_file = root.attrib.get("xar")
            if not xar_file:
                beh = root.find(".//Behavior")
                if beh is not None:
                    xar_file = beh.attrib.get("xar")
            if not xar_file:
                xars = sorted(glob.glob(os.path.join(arg_path, "*.xar")))
                if not xars:
                    raise RuntimeError("Aucun .xar référencé dans %s" % pml)
                xar_file = xars[0]
            if not os.path.isabs(xar_file):
                xar_file = os.path.join(arg_path, xar_file)
            # audio heuristique
            audio = None
            for ext in AUDIO_EXT:
                lst = sorted(glob.glob(os.path.join(arg_path, "*" + ext)))
                if lst:
                    audio = _abspath(lst[0]); break
            return ("xar", _abspath(xar_file), audio)
        except Exception as e:
            raise RuntimeError("Erreur PML %s : %s" % (pml, e))

    # Fichier (tolérant)
    low = arg_path.lower()
    if low.endswith(".qianim"):
        return ("qianim", arg_path, None)
    if low.endswith(".xar"):
        # tenter de trouver un audio adjacent
        folder = os.path.dirname(arg_path)
        base = os.path.splitext(os.path.basename(arg_path))[0]
        audio = None
        for ext in AUDIO_EXT:
            cand = _first_existing(os.path.join(folder, base + ext))
            if cand:
                audio = cand; break
        return ("xar", arg_path, audio)

    # Si c'est un fichier sans extension explicite, essaye .qianim prioritaire
    if os.path.exists(arg_path):
        q = arg_path + ".qianim"
        x = arg_path + ".xar"
        if os.path.exists(q):
            return ("qianim", q, None)
        if os.path.exists(x):
            return ("xar", x, None)

    raise RuntimeError("Chemin invalide ou format non supporté: %s" % arg_path)

def main():
    if len(sys.argv) < 2:
        print("Usage: python animation_player.py <fichier .qianim|.xar | dossier>")
        sys.exit(1)
    arg = sys.argv[1]

    try:
        mode, path, audio_override = resolve_input(arg)
    except Exception as e:
        print("[ERROR]", e)
        # Aide au debug
        try:
            import os
            print("[DEBUG] pwd:", os.getcwd())
            print("[DEBUG] exists:", os.path.exists(_abspath(arg)))
            print("[DEBUG] isfile:", os.path.isfile(_abspath(arg)))
        except Exception:
            pass
        sys.exit(2)

    app = qi.Application(["AnimPlayer", "--qi-url=tcp://127.0.0.1:9559"])
    app.start()
    session = app.session

    if mode == "qianim":
        player = QianimPlayer(session, path, audio_override=None)
    else:
        player = XarPlayer(session, path, audio_override=audio_override)

    player.run()

if __name__ == "__main__":
    main()
