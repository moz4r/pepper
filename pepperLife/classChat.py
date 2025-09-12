# -*- coding: utf-8 -*- 
# classChat.py - Chat logic using OpenAI

from openai import OpenAI

class Chat(object):
    def __init__(self, config):
        self.config = config
        self._client = None

    def client(self):
        if self._client is None:
            self._client = OpenAI(timeout=15.0)
        return self._client

    def chat(self, user_text, hist):
        msgs = [{"role":"system","content":self.config['openai']['system_prompt']}]
        for role, content in hist:
            msgs.append({"role": role, "content": content})
        msgs.append({"role":"user","content":user_text})
        resp = self.client().chat.completions.create(
            model=self.config['openai']['chat_model'], messages=msgs, temperature=0.6, max_tokens=60
        )
        return resp.choices[0].message.content.strip().replace("\n"," ").strip()
