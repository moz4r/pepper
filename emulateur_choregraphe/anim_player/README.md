# Xar Player

Lecteur Python d'animations **.xar** issues de Choregraphe pour robots Pepper/QiOS 2.9.
Il peut exécuter un fichier `.xar` directement ou analyser un dossier de comportement
contenant un fichier `.pml` et un audio optionnel.

Les modules de classes portent désormais l'extension `.class`.

## Installation

```bash
pip install qi
```

Le script doit être lancé depuis une machine ayant accès au robot sur le port `9559`.

## Utilisation

### Fichier `.xar`

```bash
python animation_player.py chemin/vers/animation.xar
```

### Dossier de comportement

```bash
python animation_player.py chemin/vers/dossier_comportement
```

Le premier fichier `.pml` trouvé est analysé pour localiser le `.xar` et un audio
(`.ogg`, `.mp3`, `.wav`). L'audio est joué en parallèle de l'animation.

## Variables d'environnement

- `XAR_SPEED_FACTOR` : facteur global appliqué aux temps (1.0 = vitesse normale).
- `XAR_VEL_SAFETY` : sécurité sur la vitesse maximale des articulateurs (par défaut 0.98).

## Fonctionnement

1. Réveille le robot et active les moteurs si nécessaire.
2. Désactive temporairement les modules aléatoires (`AutonomousBlinking`, `BackgroundMovement`, etc.).
3. Lecture des courbes du `.xar` et des éventuels sons.
4. Lancement d'une trajectoire PMT associée si elle est présente.
5. Réactivation des modules aléatoires à la fin de l'animation.

## Limites

Seules les boîtes **Animation** et **Say** sont actuellement gérées.
