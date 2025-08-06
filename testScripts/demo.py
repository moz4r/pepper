# -*- coding: utf-8 -*-
import qi, time

def ensure_awake(session):
    """
    Vérifie que Pepper est réveillé et en mode 'interactive'
    - wakeUp() : alimente les moteurs (sinon ils sont mous)
    - setStiffnesses("Body", 1.0) : applique une rigidité maximale sur tout le corps
    - AutonomousLife : assure que l'état est 'interactive' (pas 'disabled' ou 'solitary')
    """
    motion = session.service("ALMotion")
    life = session.service("ALAutonomousLife")
    try:
        if not motion.robotIsWakeUp():
            print("[INFO] Robot endormi, réveil en cours...")
            motion.wakeUp()
            time.sleep(1)
        motion.setStiffnesses("Body", 1.0)
        if life.getState() != "interactive":
            life.setState("interactive")
            print("[OK] AutonomousLife -> interactive")
        print("[OK] Moteurs actifs et robot éveillé")
    except Exception as e:
        print("[ERREUR] ensure_awake :", e)

def pepper_docile(session):
    """
    Mode docile :
    - Désactive les mouvements autonomes (random OFF)
    - Effectue un test moteur complet (tête, bras, base)
    """
    ensure_awake(session)
    tts = session.service("ALTextToSpeech")
    motion = session.service("ALMotion")

    # Liste des modules d'autonomie gênants (aléatoires)
    modules = [
        "ALSpeakingMovement",
        "ALListeningMovement",
        "ALBackgroundMovement",
        "BasicAwareness",
    ]
    for name in modules:
        try:
            srv = session.service(name)
            srv.setEnabled(False)
            print("[OK] {} désactivé".format(name))
        except Exception as e:
            print("[--] Impossible de désactiver {} : {}".format(name, e))

    tts.say("Mode docile activé. Test des moteurs.")

    # --- MOUVEMENT DE LA TÊTE ---
    # setAngles(jointNames, targetAngles, fractionMaxSpeed)
    # - jointNames : liste des articulations (ex: ["HeadYaw","HeadPitch"])
    # - targetAngles : liste des angles CIBLE en radians
    # - fractionMaxSpeed : vitesse de mouvement entre 0.0 (lent) et 1.0 (max)
    #   Exemple : 0.2 = 20% de la vitesse max, plus fluide et plus sûr.
    motion.setAngles(["HeadYaw", "HeadPitch"], [0.4, -0.2], 0.2)
    time.sleep(2)
    motion.setAngles(["HeadYaw", "HeadPitch"], [-0.4, 0.2], 0.2)
    time.sleep(2)
    motion.setAngles(["HeadYaw", "HeadPitch"], [0.0, 0.0], 0.2)

    # --- BRAS DROIT ---
    # RShoulderPitch : monte/descend l'épaule (0 = bras en avant, ~1.5 = bras vers le bas)
    # RShoulderRoll  : écarte/rapproche le bras du corps (positif = écarté)
    motion.setAngles(["RShoulderPitch", "RShoulderRoll"], [1.0, -0.2], 0.2)
    time.sleep(2)
    motion.setAngles(["RShoulderPitch", "RShoulderRoll"], [1.4, 0.0], 0.2)

    # --- BRAS GAUCHE ---
    motion.setAngles(["LShoulderPitch", "LShoulderRoll"], [1.0, 0.2], 0.2)
    time.sleep(2)
    motion.setAngles(["LShoulderPitch", "LShoulderRoll"], [1.4, 0.0], 0.2)

    # --- BASE (rotation) ---
    # moveTo(x, y, theta)
    # - x : déplacement vers l'avant en mètres (positif = avance, négatif = recule)
    # - y : déplacement latéral en mètres (positif = gauche, négatif = droite)
    # - theta : rotation en radians (positif = tourne à gauche, négatif = droite)
    # Exemple : theta = 0.3 ~ rotation d'environ 17 degrés
    tts.say("Je tourne légèrement ma base.")
    motion.moveTo(0.0, 0.0, 0.3)   # tourne à gauche
    time.sleep(2)
    motion.moveTo(0.0, 0.0, -0.3)  # tourne à droite
    time.sleep(2)
    # petit pas en avant
    motion.moveTo(0.1, 0.0, 0.0)   # avance de 10 cm
    time.sleep(2)
    # retour sur place
    motion.moveTo(0.0, 0.0, 0.0)

    # --- RETOUR NEUTRE ---
    motion.setAngles([
        "HeadYaw","HeadPitch",
        "RShoulderPitch","RShoulderRoll",
        "LShoulderPitch","LShoulderRoll"
    ], [0.0,0.0,1.4,0.0,1.4,0.0], 0.2)

    tts.say("Test des moteurs terminé.")

def pepper_random(session):
    """
    Mode vivant :
    - Réactive les mouvements autonomes (random ON)
    """
    ensure_awake(session)
    tts = session.service("ALTextToSpeech")

    modules = [
        "ALSpeakingMovement",
        "ALListeningMovement",
        "ALBackgroundMovement",
        "BasicAwareness",
    ]
    for name in modules:
        try:
            srv = session.service(name)
            srv.setEnabled(True)
            print("[OK] {} activé".format(name))
        except Exception as e:
            print("[--] Impossible d'activer {} : {}".format(name, e))

    tts.say("Retour en mode vivant.")

if __name__ == "__main__":
    session = qi.Session()
    session.connect("tcp://127.0.0.1:9559")

    pepper_docile(session)
    time.sleep(5)
    pepper_random(session)
