# PepperLife - NaoQI / Python3 / GPT

<img width="1160" height="761" alt="image" src="https://github.com/user-attachments/assets/f0549f60-1085-4d97-abdf-b462770610f9" />


**PepperLife** est un projet open-source qui vise à doter le robot **Pepper** de capacités d'interaction avancées en le connectant à des modèles de langage (LLM) de pointe comme GPT-4o, GPT-4o-mini ou GPT-5 d'OpenAI, selon votre configuration. Il transforme Pepper en un assistant plus intelligent, capable de comprendre, de voir, de parler et d'interagir de manière fluide et naturelle.

---

## 🚀 Fonctionnalités Principales

- **🗣️ Conversation Intelligente** : Dialogue fluide et naturel avec sélection dynamique entre `gpt-4o-mini`, `gpt-4o`, `gpt-5` (ou tout modèle compatible configuré).
- **👁️ Vision Intégrée** : Demandez à Pepper ce qu'il voit ("que vois-tu ?") et il décrira la scène en utilisant ses caméras.
- **🎙️ Transcription en Temps Réel** : Écoute active via streaming audio et transcription précise avec `gpt-4o-mini-transcribe` (ou `whisper-1` en solution de repli).
- **🕺 Animations Dynamiques** : Le LLM peut déclencher des animations contextuelles (`^start(...)`) à partir d'un catalogue généré automatiquement, rendant l'interaction plus vivante.
- **💡 Indicateurs LED & Animations Intuitifs** : Les LEDs passent en **Bleu** (écoute), **Violet** (réflexion), **Blanc** (parole/attente) et des boucles d'animations dédiées différencient réflexion et prise de parole.
- **🔇 Gestion Audio Avancée** : Systèmes anti-larsen et anti-bruit pour une meilleure qualité audio.
- **🌐 Interface Web de Contrôle** : Une interface web complète pour gérer le robot, surveiller son état, et configurer ses fonctionnalités.
- **🧩 Architecture Modulaire** : Le système est conçu en classes Python normalisées (`classLEDs`, `classAnimation`, etc.) pour une maintenance et une évolution facilitées.
- **⚙️ Service Unifié NAOqi** : `pepper_life_service.py` harmonise les API NAOqi 2.5 et 2.9 via un service commun, garantissant une compatibilité multi-firmware.

---

## 🔧 Comment ça marche ?

Le système suit un pipeline simple mais puissant :

1.  **Écoute** : Le microphone de Pepper capture l'audio en continu.
2.  **Transcription (STT)** : L'audio est envoyé à l'API d'OpenAI pour être transformé en texte.
3.  **Compréhension (Chat)** : Le texte est envoyé au modèle de langage (LLM) pour générer une réponse.
4.  **Action** : La réponse est utilisée pour :
    *   Faire parler le robot (TTS) avec animations de parole synchronisées.
    *   Déclencher des animations de réflexion ou scénarisées selon le contexte.
    *   Exécuter des commandes spécifiques.

---

## 🛠️ Prérequis

### Matériel & Logiciel
- Un robot **Pepper** avec **NAOqi 2.5, 2.9 ou une version compatible**.
- **Python 3** installé sur le robot (via l'application `python3nao`) ou sur un PC avec le SDK NAOqi.
- Une **clé d'API OpenAI** valide.

### Services NAOqi
Le projet nécessite que les services suivants soient actifs sur le robot :
- `ALAudioDevice`
- `ALTextToSpeech`
- `ALLeds`
- `ALMotion`
- `ALRobotPosture`
- `ALAnimatedSpeech`
- `ALVideoDevice`
- `ALBehaviorManager`

`PepperLifeService` encapsule ces dépendances et route automatiquement vers les implémentations NAOqi 2.5 ou 2.9 adaptées, sans configuration supplémentaire.

---

## 📦 Installation

Il existe deux méthodes principales pour installer l'application sur votre robot.

### Méthode 1 : Via Choregraphe
1.  Ouvrez **Choregraphe** et connectez-vous à votre robot.
2.  Installez le fichier `pepperlife.pkg` via le panneau de gestion des applications.

### Méthode 2 : En Ligne de Commande
1.  Transférez le fichier `pepperlife.pkg` sur le robot (par exemple, dans `/home/nao/`) en utilisant `scp` ou `sftp`.
2.  Connectez-vous au robot en SSH.
3.  Exécutez la commande suivante :
    ```bash
    qicli call PackageManager.install /home/nao/pepperlife.pkg
    ```

### Post-installation : Dépendances Python
Au premier lancement, le script tentera d'installer les dépendances Python requises (comme `openai`). Si cette étape échoue, connectez-vous en SSH au robot et installez-les manuellement :
```bash
# Mettre à jour pip
/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh -m pip install --upgrade pip

# Installer les dépendances
/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh -m pip install openai
```

---

## 🚀 Utilisation

Une fois l'application installée, le service de lancement démarre automatiquement avec le robot.

1.  Assurez-vous que votre ordinateur est sur le même réseau que le robot.
2.  Ouvrez un navigateur web et accédez à l'adresse suivante, en remplaçant `<IP_DU_ROBOT>` par l'adresse IP de votre Pepper :
    ```
    http://<IP_DU_ROBOT>:8080
    ```
3.  Depuis cette interface, vous pouvez :
    *   **Démarrer et arrêter** les services principaux de PepperLife.
    *   **Activer, désactiver ou choisir** le moteur GPT utilisé (4o-mini rapide, 4o complet, 5 raisonnement minimal).
    *   **Gérer et lancer** des applications ou des animations.
    *   **Consulter les logs** et l'état du robot.

### Configuration de la clé OpenAI
Pour que le chatbot fonctionne, vous devez fournir votre clé d'API OpenAI. Vous pouvez le faire via l'interface web dans l'onglet **Settings**.

### Personnalisation de la synthèse vocale
Certaines prononciations problématiques peuvent être corrigées en éditant le fichier `lang/map/tts_replacements.txt`. Chaque ligne suit la forme `mot_original=mot_remplace` (les lignes vides ou précédées de `#` sont ignorées). Pepper remplacera ces mots juste avant l'envoi au TTS.



## 🙌 Contribution

Les contributions sont les bienvenues ! Si vous souhaitez améliorer PepperLife, n'hésitez pas à forker le projet, créer une branche pour votre fonctionnalité et soumettre une Pull Request.

## 📄 Licence

Ce projet est distribué sous la licence Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0). Voir le fichier `LICENSE` pour le texte complet.
