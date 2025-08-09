#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import glob
import xml.etree.ElementTree as ET
import qi
from xar_player import XarPlayer

def resolve_input_path(arg_path):
    """
    Retourne (xar_path, audio_override or None).
    - Si arg_path est un .xar -> (arg_path, None)
    - Si arg_path est un dossier -> parse *.pml pour trouver le xar et un audio
    """
    arg_path = os.path.abspath(arg_path)
    if os.path.isfile(arg_path) and arg_path.lower().endswith(".xar"):
        return arg_path, None

    if os.path.isdir(arg_path):
        # Chercher un .pml dans ce dossier (prend le premier trouvé)
        pmls = sorted(glob.glob(os.path.join(arg_path, "*.pml")))
        if not pmls:
            raise RuntimeError("Aucun fichier .pml trouvé dans: {}".format(arg_path))
        pml = pmls[0]
        try:
            tree = ET.parse(pml)
            root = tree.getroot()
        except Exception as e:
            raise RuntimeError("Impossible de parser le .pml '{}': {}".format(pml, e))

        # BehaviorDescription -> @src (répertoire), @xar (fichier)
        beh = root.find(".//BehaviorDescriptions/BehaviorDescription")
        if beh is None:
            raise RuntimeError("Pas de BehaviorDescription dans: {}".format(pml))

        src_dir = beh.attrib.get("src", ".")
        xar_file = beh.attrib.get("xar")
        if not xar_file:
            raise RuntimeError("Attribut 'xar' manquant dans BehaviorDescription de: {}".format(pml))

        xar_path = os.path.join(arg_path, src_dir, xar_file)
        if not os.path.exists(xar_path):
            raise RuntimeError("Fichier XAR introuvable: {}".format(xar_path))

        # Optionnel: chercher un audio dans <Resources>
        audio_override = None
        resources = root.find(".//Resources")
        if resources is not None:
            for f in resources.findall("File"):
                src = f.attrib.get("src", "")
                if src.lower().endswith((".ogg", ".mp3", ".wav")):
                    cand = os.path.join(arg_path, src)
                    if os.path.exists(cand):
                        audio_override = cand
                        break

        return xar_path, audio_override

    raise RuntimeError("Chemin invalide: {}".format(arg_path))

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py path/to/behavior.xar OR path/to/folder_with_pml")
        sys.exit(1)

    arg = sys.argv[1]
    try:
        xar_path, audio_override = resolve_input_path(arg)
    except Exception as e:
        print("[ERROR]", e)
        sys.exit(2)

    app = qi.Application(["XarPlayer", "--qi-url=tcp://127.0.0.1:9559"])
    app.start()
    session = app.session

    player = XarPlayer(session, xar_path, audio_override=audio_override)
    player.run()

if __name__ == "__main__":
    main()
