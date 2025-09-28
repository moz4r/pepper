# PepperLife 0.5

![pepperlife_edited](https://github.com/user-attachments/assets/fba8f19b-ef94-4246-bdc5-7bd2d5027dfb)

Pipeline léger **NAOqi + OpenAI** pour **Pepper** :

- 🎙️ Écoute via streaming audio
- 🔤 STT OpenAI (`gpt-4o-mini-transcribe`, fallback `whisper-1`)
- 💬 Chat (`gpt-4o-mini`)
- 👁️ **Vision** : demandez "que vois-tu ?" pour que Pepper décrive la scène.
- 💡 LEDs synchronisées : **Bleu** (REC) → **Violet** (réflexion) → **Blanc** (parole/idle)
- 🕺 **Gestion dynamique des animations** : le LLM peut déclencher des animations (`^start(...)`) parmi un catalogue généré automatiquement au démarrage.
- 🔇 Anti-larsen & anti-bruit (blacklist + heuristiques)
- 🧩 Architecture par classes normalisées : `classLEDs.py`, `classAnimation.py`, `classRobotBehavior.py`
- ✔️ Interface web de contrôle et de diagnostique du robot

---

## Prérequis

- **Pepper NAOqi 2.7 -> 2.9**
- **Python 3** (sur Pepper via l app `python3nao`, ou PC avec SDK NAOqi)
- **Clé OpenAI** (`OPENAI_API_KEY`)
- Services NAOqi : **ALAudioDevice**, **ALTextToSpeech**, **ALLeds**, **ALMotion**, **ALRobotPosture**, **ALAnimatedSpeech**, **ALVideoDevice**

```bash



## Installation

Il y a deux méthodes pour installer l'application sur le robot.

### Méthode 1 : Choregraphe (pour NAOqi ~2.7)

1.  Ouvrez Choregraphe et connectez-vous à votre robot.
2.  Sélectionnez le fichier `pepperlife.pkg` à installer.

### Méthode 2 : Ligne de commande (pour NAOqi 2.9/2.7)

1.  Transférez le fichier `pepperlife.pkg` sur le robot (par exemple dans `/home/nao/`) via `scp` ou `sftp`.
2.  Connectez-vous au robot en SSH.
3.  Lancez la commande :
    ```bash
    qicli call PackageManager.install /home/nao/pepperlife.pkg
    ```

### Post-installation : Dépendances

Au premier lancement, le script essaiera d'installer les dépendances Python (comme `openai`) automatiquement. Si cela échoue, connectez-vous en SSH au robot et lancez :

```bash
/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh -m pip install --upgrade pip
/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh -m pip install openai
```


### Utilisation

Une fois l'application installée, le service de lancement démarre automatiquement avec le robot.

1.  Ouvrez un navigateur web sur un ordinateur connecté au même réseau que le robot.
2.  Rendez-vous à l'adresse suivante, en remplaçant `<IP_DU_ROBOT>` par l'adresse IP de votre Pepper :
    ```
    http://<IP_DU_ROBOT>:8080
    ```
3.  Vous accéderez à l'interface web qui vous permettra de démarrer, arrêter et configurer l'application PepperLife.

<img width="1793" height="1094" alt="image" src="https://github.com/user-attachments/assets/6023eaa0-73cd-4122-aaf8-fed1d9683fe4" />

<img width="1788" height="912" alt="image" src="https://github.com/user-attachments/assets/80b240a6-6386-4046-a6a1-7a6ed2476ead" />


