# PepperLife

Pipeline léger **NAOqi + OpenAI** pour **Pepper** :

- 🎙️ Écoute locale (ALAudioDevice 16 kHz) + VAD court
- 🔤 STT OpenAI (`gpt-4o-mini-transcribe`, fallback `whisper-1`)
- 💬 Chat (`gpt-4o-mini`) avec *balises d’actions* exécutées via NAOqi
- 💡 LEDs synchronisées : **Bleu** (REC) → **Violet** (réflexion) → **Blanc** (parole/idle)
- 🕺 Parole & mouvements en parallèle (TTS non bloquant via `post.say` si dispo)  //TODO
- 🔇 Anti-larsen & anti-bruit (blacklist + heuristiques)
- 🧩 Architecture par classes normalisées : `classLEDs.py`, `classActions.py`, `classRobotBehavior.py`
- ✔️ Version actuelle : **0.0.1**
