#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.dont_write_bytecode = True

import sys
import os
import glob
import xml.etree.ElementTree as ET
import qi

from qianim_player import QianimPlayer

# Pas de .pyc
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

AUDIO_EXT = (".wav", ".mp3", ".ogg")


def _abspath(p):
    return os.path.realpath(os.path.expanduser(p))


def _find_audio_for_base(folder, base):
    """Cherche <base>.(wav|mp3|ogg) dans folder/ puis folder/audio|sounds/."""
    for ext in AUDIO_EXT + tuple(e.upper() for e in AUDIO_EXT):
        cand = os.path.join(folder, base + ext)
        if os.path.isfile(cand):
            return cand
        for sub in ("audio", "sounds"):
            cand2 = os.path.join(folder, sub, base + ext)
            if os.path.isfile(cand2):
                return cand2
    return None


def _find_single_audio(folder):
    """Retourne l'unique audio présent dans folder/ ou folder/audio|sounds/, sinon None."""
    candidates = []
    for sub in ("", "audio", "sounds"):
        subdir = os.path.join(folder, sub) if sub else folder
        if not os.path.isdir(subdir):
            continue
        for ext in (".wav", ".mp3", ".ogg", ".WAV", ".MP3", ".OGG"):
            candidates.extend(glob.glob(os.path.join(subdir, "*" + ext)))
    # dédoublonner
    seen = set()
    uniq = []
    for c in candidates:
        if c not in seen:
            uniq.append(c)
            seen.add(c)
    return uniq[0] if len(uniq) == 1 else None


def _pml_find_audio_and_xar(pml_path):
    """Parse un .pml et renvoie (xar_abs, audio_abs_or_None)."""
    try:
        tree = ET.parse(pml_path)
        root = tree.getroot()
    except Exception as e:
        raise RuntimeError("PML invalide: %s" % e)

    base_dir = os.path.dirname(pml_path)

    # 1) Résoudre behavior.xar
    xar_rel = None
    # a) BehaviorDescriptions/BehaviorDescription @xar (ou src)
    bd_parent = root.find(".//BehaviorDescriptions")
    if bd_parent is not None:
        bd = bd_parent.find(".//BehaviorDescription")
        if bd is not None:
            xar_rel = bd.attrib.get("xar") or bd.attrib.get("src")
    if not xar_rel:
        # b) attribut racine (rare) ou <Behavior>
        xar_rel = root.attrib.get("xar")
        if not xar_rel:
            beh = root.find(".//Behavior")
            if beh is not None:
                xar_rel = beh.attrib.get("xar") or beh.attrib.get("src")
    if xar_rel:
        xar_abs = _abspath(os.path.join(base_dir, xar_rel))
    else:
        # fallback: premier .xar aux côtés du .pml
        xars = sorted(glob.glob(os.path.join(base_dir, "*.xar")))
        if not xars:
            raise RuntimeError("Aucun behavior.xar trouvé pour %s" % pml_path)
        xar_abs = _abspath(xars[0])

    # 2) Audio déclaré dans <Resources>
    audio_abs = None
    res_parent = root.find(".//Resources")
    if res_parent is not None:
        for f in res_parent.findall(".//File"):
            src = f.attrib.get("src") or ""
            low = src.lower()
            if low.endswith(AUDIO_EXT):
                audio_abs = _abspath(os.path.join(base_dir, src))
                break

    return xar_abs, audio_abs


def resolve_input(arg_path):
    """
    Retourne (mode, path, audio_override)
      - Dossier: .qianim prioritaire, sinon .pml (extrait audio & behavior.xar), sinon .xar (heuristique audio)
      - Fichier: .qianim, .pml, .xar (avec détection audio associée)
    """
    if not arg_path:
        raise RuntimeError("Aucun argument fourni.")
    arg_path = _abspath(arg_path)

    if os.path.isdir(arg_path):
        # 1) .qianim prioritaire
        qians = sorted(glob.glob(os.path.join(arg_path, "*.qianim")))
        if qians:
            qf = _abspath(qians[0])
            base = os.path.splitext(os.path.basename(qf))[0]
            audio = _find_audio_for_base(os.path.dirname(qf), base)
            if not audio:
                audio = _find_single_audio(os.path.dirname(qf))
            print("[DEBUG] QIANIM dir -> %s audio: %s" % (qf, audio))
            return ("qianim", qf, audio)

        # 2) .pml ensuite
        pmls = sorted(glob.glob(os.path.join(arg_path, "*.pml")))
        if pmls:
            xar_abs, audio_abs = _pml_find_audio_and_xar(_abspath(pmls[0]))
            print("[DEBUG] PML -> XAR: %s audio: %s" % (xar_abs, audio_abs))
            return ("xar", xar_abs, audio_abs)

        # 3) .xar enfin
        xars = sorted(glob.glob(os.path.join(arg_path, "*.xar")))
        if xars:
            xf = _abspath(xars[0])
            base = os.path.splitext(os.path.basename(xf))[0]
            audio = _find_audio_for_base(arg_path, base)
            if not audio:
                audio = _find_single_audio(arg_path)
            print("[DEBUG] XAR dir -> %s audio: %s" % (xf, audio))
            return ("xar", xf, audio)

        raise RuntimeError("Aucun .qianim/.pml/.xar trouvé dans: %s" % arg_path)

    # Fichier
    low = arg_path.lower()
    if low.endswith(".qianim"):
        folder = os.path.dirname(arg_path)
        base = os.path.splitext(os.path.basename(arg_path))[0]
        audio = _find_audio_for_base(folder, base)
        if not audio:
            audio = _find_single_audio(folder)
        print("[DEBUG] QIANIM file -> audio: %s" % audio)
        return ("qianim", arg_path, audio)

    if low.endswith(".pml"):
        xar_abs, audio_abs = _pml_find_audio_and_xar(arg_path)
        print("[DEBUG] PML file -> XAR: %s audio: %s" % (xar_abs, audio_abs))
        return ("xar", xar_abs, audio_abs)

    if low.endswith(".xar"):
        folder = os.path.dirname(arg_path)
        base = os.path.splitext(os.path.basename(arg_path))[0]
        audio = _find_audio_for_base(folder, base)
        if not audio:
            audio = _find_single_audio(folder)
        print("[DEBUG] XAR file -> audio: %s" % audio)
        return ("xar", arg_path, audio)

    raise RuntimeError("Chemin invalide ou format non supporté: %s" % arg_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python animation_player.py <fichier .qianim|.pml|.xar | dossier>")
        sys.exit(1)
    arg = sys.argv[1]

    try:
        mode, path, audio_override = resolve_input(arg)
    except Exception as e:
        print("[ERROR]", e)
        sys.exit(2)

    app = qi.Application(["AnimPlayer", "--qi-url=tcp://127.0.0.1:9559"])
    app.start()
    session = app.session

    # Player unique pour .qianim ET .xar (via xar_parser côté player)
    player = QianimPlayer(session, path, audio_override=audio_override)
    player.run()


if __name__ == "__main__":
    main()
