"""Tenká vrstva nad AI (výchozí Gemini free tier, volitelně Claude). Vrací JSON."""
import json
import os
import time

from config import CONFIG
from util import session


class QuotaExhausted(Exception):
    pass


class AI:
    def __init__(self):
        cfg = CONFIG["ai"]
        self.provider = os.environ.get("AI_PROVIDER", cfg["provider"])
        self.max_calls = cfg["max_calls_per_run"]
        self.pause = cfg["pause_seconds"]
        self.calls = 0
        self.model = cfg.get("gemini_model")
        self.key = os.environ.get("GEMINI_API_KEY") if self.provider == "gemini" else os.environ.get("ANTHROPIC_API_KEY")
        self._last = 0.0

    @property
    def available(self):
        return bool(self.key) and self.calls < self.max_calls

    def json(self, prompt, max_tokens=4096):
        if not self.key:
            raise QuotaExhausted("chybí API klíč")
        if self.calls >= self.max_calls:
            raise QuotaExhausted("vyčerpán limit volání pro tento běh")
        wait = self.pause - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self.calls += 1
        try:
            text = self._gemini(prompt, max_tokens) if self.provider == "gemini" else self._claude(prompt, max_tokens)
        finally:
            self._last = time.time()
        return _parse_json(text)

    def search_json(self, prompt):
        """Dotaz s vyhledáváním Google (jen Gemini) – pro jednorázové dohledání webů."""
        if self.provider != "gemini" or not self.key:
            raise QuotaExhausted("vyhledávání vyžaduje Gemini klíč")
        wait = self.pause - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self.calls += 1
        try:
            text = self._gemini(prompt + "\n\nOdpověz pouze JSON objektem.", 1024, search=True)
        finally:
            self._last = time.time()
        return _parse_json(text)

    # --- Gemini -----------------------------------------------------------
    def _gemini(self, prompt, max_tokens, retried=False, search=False):
        model = CONFIG["ai"].get("gemini_search_model", self.model) if search else self.model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        gen = {"maxOutputTokens": max_tokens, "temperature": 0.1}
        if not search:
            gen["responseMimeType"] = "application/json"
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}
        if search:
            body["tools"] = [{"google_search": {}}]
        r = session.post(url, headers={"x-goog-api-key": self.key}, json=body, timeout=120)
        if r.status_code == 404 and not retried and not search:
            self.model = self._pick_gemini_model()
            return self._gemini(prompt, max_tokens, retried=True)
        if r.status_code == 429:
            if not retried and "PerMinute" in r.text:
                time.sleep(65)
                return self._gemini(prompt, max_tokens, retried=True, search=search)
            raise QuotaExhausted("Gemini: vyčerpaná kvóta (429)")
        r.raise_for_status()
        cand = r.json()["candidates"][0]
        return "".join(p.get("text", "") for p in cand["content"]["parts"])

    def _pick_gemini_model(self):
        r = session.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": self.key}, timeout=30)
        r.raise_for_status()
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        for want in ("flash-lite", "flash"):
            ok = sorted((n for n in names if want in n and "preview" not in n and "exp" not in n), reverse=True)
            if ok:
                print(f"  AI: model {self.model} nenalezen, používám {ok[0]}")
                return ok[0]
        raise RuntimeError("Nenalezen žádný vhodný Gemini model")

    # --- Claude (záložní varianta) ----------------------------------------
    def _claude(self, prompt, max_tokens):
        r = session.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
            json={"model": CONFIG["ai"].get("claude_model", "claude-haiku-5-5"), "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt + "\n\nOdpověz pouze čistým JSON."}]},
            timeout=120,
        )
        if r.status_code == 429:
            raise QuotaExhausted("Claude: rate limit")
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])


def _parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=0)
        end = max(text.rfind("]"), text.rfind("}")) + 1
        return json.loads(text[start:end])
