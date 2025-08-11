Pepper Universal Animation Player — v0.1‑Alpha

Un lecteur afin de pouvoir à nouveau lancer ( en local / sans tablette ) des animations.

État : 0.1‑Alpha — suffisamment stable pour des démos

Contenu

animation_player.py   # point d’entrée : détecte .xar/.qianim/.pml + appairage audio

Classes :
qianim_player.py      # player : drapeaux (pré‑position, start boost, time scale, audio lag, tail sleep)
random_control.py     # reset sûr : stopMove/killAll, snapshot raideur, Breath Body/Arms/Head OFF + restore
xar_parser.py         # lecteur XAR : FPS par Timeline, choix de courbe par durée (secondes), sécurité des limites
audio_control.py      # audio : appairage + lecture/stop asynchrone (NAOqi post si dispo)
services.py           # helpers services NAOqi

Prérequis

Pepper (NAOqi 2.x) — testé sur NAOqi 2.9 (JULIETTE_Y20). Le manifeste cible NAOqi ≥ 2.3.

Python sur le robot (image standard Pepper).

Pas de .pyc : l’écriture de bytecode est désactivée par défaut.



Démarrage rapide

SSH sur le robot puis :

python animation_player.py /chemin/vers/behavior.xar
# ou un dossier / un .qianim / un .pml (l’audio est auto‑détecté quand c'est possible)

Le player choisit automatiquement le mode :

.xar : parse via xar_parser.py, exécute une passe angleInterpolation

.qianim : lit les courbes et exécute de la même façon

.pml / dossier : résout le behavior.xar et tente d’associer l’audio voisin

Fonctionnalités clés (0.1‑Alpha)

Reset propre avant animation

motion.stopMove() + motion.killAll() au début (nettoyage des tâches résiduelles)

Breath OFF sur Body, Arms, Head, avec snapshot + restore en fin

Stiffness Body → 1.0 pendant l’anim (snapshot + restore)

Note : on ne touche pas à ALAutonomousLife (pas d’endormissement involontaire).

Lecture XAR fidèle

FPS pris sur la Timeline parente (25/30 fps correctement gérés)

Choix de la courbe « principale » par durée (secondes), pas par nombre de frames

Conversion deg→rad si unit=0, timestamps arrondis à 3 décimales

Sécurité vitesse : si getLimits(vmax) est dépassé, le temps est étiré localement (log [SAFE]).

Démarrage / fin propres

Pré‑position optionnelle vers la 1ere clé

Start boost optionnel : setAngles immédiat vers la 1ere clé

motion.stopMove() juste après angleInterpolation(...) (fin nette)


Audio

Détection automatique du fichier audio voisin (ogg/mp3/wav)

NAOqi post.playFile(...) si disponible (non‑bloquant), sinon fallback thread

TTS box (Say)

Support des boîtes Say du XAR : bloquant si la ressource type="Lock" est présente, sinon asynchrone via tts.post.say quand disponible. Fallback propre si post est absent.

