# -*- coding: utf-8 -*-
import qi
import time
import sys
import threading

PEPPER_IP = "127.0.0.1"
PEPPER_PORT = 9559

def main():
    session = qi.Session()
    try:
        session.connect("tcp://{}:{}".format(PEPPER_IP, PEPPER_PORT))
    except RuntimeError:
        print("Impossible de se connecter à NAOqi")
        sys.exit(1)

    print("[OK] Connecté à NAOqi 2.9")

    tts = session.service("ALTextToSpeech")
    dialog = session.service("ALDialog")
    memory = session.service("ALMemory")
    leds = session.service("ALLeds")
    motion = session.service("ALMotion")

    # Réveiller Pepper
    motion.wakeUp()
    print("[OK] Robot réveillé")

    # Stopper Nuance (Android)
    try:
        dialog.stopDialog()
        print("[OK] Dialogue Android stoppé")
    except Exception as e:
        print("[WARN] Impossible d'arrêter Nuance :", e)

    # Topic avec wildcards
    topic_content = u"""
    topic: ~wildcards()
    language: frf

    u:(* bonjour *) Salut humain $1
    u:(merci) de rien
    u:(caliban) Kamoulox !
    u:(*) J'ai entendu $1

    """

    try:
        topic_name = dialog.loadTopicContent(topic_content)
        dialog.activateTopic(topic_name)
        dialog.subscribe("PepperDialog")
        print("[OK] Topic wildcards activé")
    except Exception as e:
        print("[ERREUR] Impossible de lancer ALDialog :", e)
        sys.exit(1)

    listening = {"active": True, "running": True}

    # LEDs animées pendant écoute
    def rotate_face_leds():
        while listening["running"]:
            try:
                if listening["active"]:
                    leds.rotateEyes(0x0000FF, 1.0, 0.3)  # bleu
                else:
                    leds.fadeRGB("FaceLeds", 0xFFFFFF, 0.5)
                time.sleep(0.5)
            except RuntimeError:
                break

    t = threading.Thread(target=rotate_face_leds)
    t.setDaemon(True)
    t.start()

    # Callback pour afficher le contenu
    def on_input(value):
        print("[DEBUG] ALDialog a entendu :", value)
        if value:
            val = value.lower()
            listening["active"] = False
            leds.fadeRGB("FaceLeds", 0x0000FF, 0.3)
            tts.say("Tu as dit " + value)
            listening["active"] = True

    subscriber = memory.subscriber("Dialog/LastInput")
    subscriber.signal.connect(on_input)

    tts.say("Je suis prêt. Dis une phrase avec ou sans mot-clé.")
    print("[INFO] Parle maintenant...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Fin du test")
        listening["running"] = False
        try:
            dialog.unsubscribe("PepperDialog")
            dialog.deactivateTopic(topic_name)
            dialog.unloadTopic(topic_name)
        except:
            pass
        leds.fadeRGB("FaceLeds", 0xFFFFFF, 0.5)
        motion.rest()

if __name__ == "__main__":
    main()
