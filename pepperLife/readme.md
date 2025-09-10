# PepperLife 0.0.2

![pepperlife_edited](https://github.com/user-attachments/assets/fba8f19b-ef94-4246-bdc5-7bd2d5027dfb)


Pipeline léger **NAOqi + OpenAI** pour **Pepper** :

- 🎙️ Écoute locale (ALAudioDevice 16 kHz) + VAD court
- 🔤 STT OpenAI (`gpt-4o-mini-transcribe`, fallback `whisper-1`)
- 💬 Chat (`gpt-4o-mini`) avec *balises d’actions* exécutées via NAOqi
- 💡 LEDs synchronisées : **Bleu** (REC) → **Violet** (réflexion) → **Blanc** (parole/idle)
- 🕺 Parole & mouvements en parallèle (TTS non bloquant via `post.say` si dispo)  //TODO
- 🔇 Anti-larsen & anti-bruit (blacklist + heuristiques)
- 🧩 Architecture par classes normalisées : `classLEDs.py`, `classActions.py`, `classRobotBehavior.py`
- ✔️ Version actuelle : **0.0.2**

---



## Prérequis

- **Pepper NAOqi 2.7(préféré) -> 2.9**
- **Python 3** (sur Pepper via l app `python3nao`, ou PC avec SDK NAOqi)
- **Clé OpenAI** (`OPENAI_API_KEY`)
- Services NAOqi : **ALAudioDevice**, **ALTextToSpeech**, **ALLeds**, **ALMotion**, **ALRobotPosture**

```bash

Réglage audio utile (sur Pepper) :
amixer sset Capture 100%


## Installation

**Chemin recommandé** : `/home/nao/pepperLife`

### 1) Cloner le dépôt
```bash
# Sur Pepper OU sur PC
git clone https://github.com/moz4r/pepper.git
cd pepper/pepperLife
/home/nao/.local/share/PackageManager/apps/python3nao/bin/python3 -m pip install openai



### Configuration

La configuration se fait maintenant via le fichier `config.json`.
Une fois le script lancé, un fichier `config.json` est créé à partir de `config.json.default`.

Modifiez `config.json` pour y mettre vos propres paramètres :
- **connection**: `ip` et `port` de votre robot.
- **openai**: `api_key`, `stt_model`, `chat_model`, `system_prompt`.
- **audio**: paramètres pour la détection de la parole.
- **asr_filters**: `blacklist_strict` pour filtrer les faux positifs.
- **log**: `verbosity` pour le niveau de log.

La clé API OpenAI peut être mise soit dans `config.json` (champ `api_key`), soit via la variable d'environnement `OPENAI_API_KEY`.

###Lancement

/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh pepperLife.py

