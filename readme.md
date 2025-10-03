# PepperLife - Un Cerveau Avancé pour le Robot Pepper en mixant la force de NaoQI et GPT

![PepperLife Banner](https://github.com/user-attachments/assets/fba8f19b-ef94-4246-bdc5-7bd2d5027dfb)

**PepperLife** est un projet open-source qui vise à doter le robot **Pepper** de capacités d'interaction avancées en le connectant à des modèles de langage (LLM) de pointe comme GPT-4o d'OpenAI. Il transforme Pepper en un assistant plus intelligent, capable de comprendre, de voir, de parler et d'interagir de manière fluide et naturelle.

---

## 🚀 Fonctionnalités Principales

- **🗣️ Conversation Intelligente** : Dialogue fluide et naturel grâce au modèle `gpt-4o-mini`.
- **👁️ Vision Intégrée** : Demandez à Pepper ce qu'il voit ("que vois-tu ?") et il décrira la scène en utilisant ses caméras.
- **🎙️ Transcription en Temps Réel** : Écoute active via streaming audio et transcription précise avec `gpt-4o-mini-transcribe` (ou `whisper-1` en solution de repli).
- **🕺 Animations Dynamiques** : Le LLM peut déclencher des animations contextuelles (`^start(...)`) à partir d'un catalogue généré automatiquement, rendant l'interaction plus vivante.
- **💡 Indicateurs LED Intuitifs** : Les LEDs de Pepper changent de couleur pour indiquer son état : **Bleu** (écoute), **Violet** (réflexion), **Blanc** (parole/attente).
- **🔇 Gestion Audio Avancée** : Systèmes anti-larsen et anti-bruit pour une meilleure qualité audio.
- **🌐 Interface Web de Contrôle** : Une interface web complète pour gérer le robot, surveiller son état, et configurer ses fonctionnalités.
- **🧩 Architecture Modulaire** : Le système est conçu en classes Python normalisées (`classLEDs`, `classAnimation`, etc.) pour une maintenance et une évolution facilitées.

---

## 🔧 Comment ça marche ?

Le système suit un pipeline simple mais puissant :

1.  **Écoute** : Le microphone de Pepper capture l'audio en continu.
2.  **Transcription (STT)** : L'audio est envoyé à l'API d'OpenAI pour être transformé en texte.
3.  **Compréhension (Chat)** : Le texte est envoyé au modèle de langage (LLM) pour générer une réponse.
4.  **Action** : La réponse est utilisée pour :
    *   Faire parler le robot (TTS).
    *   Déclencher des animations.
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
    *   **Activer ou désactiver** le chatbot GPT-4o.
    *   **Gérer et lancer** des applications ou des animations.
    *   **Consulter les logs** et l'état du robot.

### Configuration de la clé OpenAI
Pour que le chatbot fonctionne, vous devez fournir votre clé d'API OpenAI. Vous pouvez le faire via l'interface web dans l'onglet **Settings**.

---

## 📸 Interface Web

Voici un aperçu de l'interface de contrôle :

**Tableau de bord principal :**
<img width="1793" height="1094" alt="Tableau de bord" src="https://github.com/user-attachments/assets/6023eaa0-73cd-4122-aaf8-fed1d9683fe4" />

**Gestion des applications et animations :**
<img width="1788" height="912" alt="Gestion des applications" src="https://github.com/user-attachments/assets/80b240a6-6386-4046-a6a1-7a6ed2476ead" />

---

## 🙌 Contribution

Les contributions sont les bienvenues ! Si vous souhaitez améliorer PepperLife, n'hésitez pas à forker le projet, créer une branche pour votre fonctionnalité et soumettre une Pull Request.

## 📄 Licence

Ce projet est distribué sous la licence MIT. Voir le fichier `LICENSE` pour plus de détails.
