"""NVIDIA Nemotron client (OpenAI-compatible) + compliance guard. Descriptive only, never advice."""
import re
import requests

from . import bidup101_config as cfg


class LLMError(Exception):
    pass


SYSTEM_PROMPT = """You are the BidUp101 assistant, an analytical and EDUCATIONAL tool for retail investors in India.
You are NOT a broker and NOT a SEBI-registered investment adviser.

NON-NEGOTIABLE RULES:
1. You may describe data, trends, indicators, sector exposure and risk signals in plain, simple language.
2. You must NEVER give personalized buy/sell/hold recommendations and NEVER tell the user what they should do with
   their money. If asked ("should I buy X?"), politely say you can't advise on that, then describe what the data shows
   (e.g. indicators, concentration, risk signals) and remind them the decision is theirs.
3. Do not predict prices or promise returns. Explain jargon in one short sentence.
4. Ground answers in the PORTFOLIO CONTEXT below. If data is missing, say so; never invent numbers.
5. Keep answers concise (under 180 words) and friendly for a beginner.

PORTFOLIO CONTEXT:
{context}"""

_ADVICE_Q = re.compile(r"\b(should i|shall i|do you recommend|would you recommend|is it (a )?good (time )?to|"
                       r"worth (buying|selling)|buy or sell|what should i (buy|sell|do)|tell me what to)\b", re.I)
_ADVICE_A = re.compile(r"\b(you should (buy|sell|hold|invest|reduce|exit|add|book)|i (would )?recommend (that you )?"
                       r"(buy|sell|hold|investing)|i suggest (you )?(buy|sell|hold)|you must (buy|sell)|"
                       r"consider (buying|selling)|it'?s a (good|great) (time to )?(buy|sell))\b", re.I)

SAFE_REPLACEMENT = ("I can't tell you what to buy, sell or hold. BidUp101 is an educational and analytical tool, "
                    "not an investment adviser. I can describe what the data shows: check the Portfolio Health "
                    "section, the stock's indicators, and the risk signals on your dashboard. The decision is yours.")


def is_advice_seeking(msg: str) -> bool:
    return bool(_ADVICE_Q.search(msg or ""))


def guard(text: str):
    """Return (safe_text, was_replaced)."""
    if _ADVICE_A.search(text or ""):
        return SAFE_REPLACEMENT, True
    return text, False


def complete(messages, max_tokens: int = 600, temperature: float = 0.2) -> str:
    key = cfg.env("NEMOTRON_API_KEY")
    if not key:
        raise LLMError("NEMOTRON_API_KEY is not configured")
    try:
        r = requests.post(f"{cfg.LLM_BASE_URL}/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": cfg.LLM_MODEL, "messages": messages,
                                "max_tokens": max_tokens, "temperature": temperature}, timeout=45)
    except requests.RequestException as e:
        raise LLMError(f"network error: {type(e).__name__}") from e
    if r.status_code != 200:
        raise LLMError(f"provider returned HTTP {r.status_code}")
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError("unexpected provider response") from e


def chat_answer(message: str, history: list, context: str) -> dict:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
    msgs += [{"role": h["role"], "content": h["content"][:1500]} for h in history[-8:]
             if h.get("role") in ("user", "assistant")]
    if is_advice_seeking(message):
        msgs.append({"role": "system", "content": "The next question seeks personal advice. Decline to advise, "
                     "then stay descriptive using the data."})
    msgs.append({"role": "user", "content": message[:1500]})
    text, replaced = guard(complete(msgs))
    return {"reply": text, "guard_triggered": replaced}
