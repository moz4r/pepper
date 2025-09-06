# PepperLife 0.0.1

![pepperlife_edited](https://github.com/user-attachments/assets/fba8f19b-ef94-4246-bdc5-7bd2d5027dfb)


Pipeline léger **NAOqi + OpenAI** pour **Pepper** :

- 🎙️ Écoute locale (ALAudioDevice 16 kHz) + VAD court
- 🔤 STT OpenAI (`gpt-4o-mini-transcribe`, fallback `whisper-1`)
- 💬 Chat (`gpt-4o-mini`) avec *balises d’actions* exécutées via NAOqi
- 💡 LEDs synchronisées : **Bleu** (REC) → **Violet** (réflexion) → **Blanc** (parole/idle)
- 🕺 Parole & mouvements en parallèle (TTS non bloquant via `post.say` si dispo)  //TODO
- 🔇 Anti-larsen & anti-bruit (blacklist + heuristiques)
- 🧩 Architecture par classes normalisées : `classLEDs.py`, `classActions.py`, `classRobotBehavior.py`
- ✔️ Version actuelle : **0.0.1**

---



## Prérequis

- **Pepper (NAOqi 2.5->2.9 / 2.5->2.7 préféré)**
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
pip3 install --user -r requirements.txt


### Configuration

# Obligatoire
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxx"

# Facultatif (des valeurs par défaut existent dans le code)
export OPENAI_STT_MODEL="gpt-4o-mini-transcribe"
export OPENAI_CHAT_MODEL="gpt-4o-mini"

# Si NAOqi n’est pas sur 127.0.0.1:9559
export PEPPER_IP="192.168.1.10"
export PEPPER_PORT="9559"

# Rendre ces exports persistants :
echo 'export OPENAI_API_KEY="sk-xxxx"' >> ~/.bashrc
source ~/.bashrc

###Lancement

/home/nao/.local/share/PackageManager/apps/python3nao/bin/runpy3.sh pepperLife.py

