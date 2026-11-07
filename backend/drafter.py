"""Turn a pasted client message into invoice fields via an OpenAI-compatible endpoint.

Never logs the pasted text. Never signs anything: the user reviews and signs.
"""
import json
import os
import urllib.request
from datetime import date

FIELDS = ("client_name", "amount_usd", "due_date", "description")


def enabled() -> bool:
    return bool(os.environ.get("SENFUND_LLM_URL") and os.environ.get("SENFUND_LLM_KEY"))


def validate(data) -> dict:
    if not isinstance(data, dict) or set(FIELDS) - set(data):
        raise ValueError("Draft is missing fields.")
    for k in ("client_name", "description", "due_date"):
        if not isinstance(data[k], str) or len(data[k]) > 500:
            raise ValueError(f"Draft field {k} is invalid.")
    date.fromisoformat(data["due_date"])
    amount = float(data["amount_usd"])
    if not amount > 0:
        raise ValueError("Draft amount must be above zero.")
    return {"client_name": data["client_name"].strip(), "amount_usd": f"{amount:.2f}",
            "due_date": data["due_date"], "description": data["description"].strip()}


def draft_invoice(text: str, url=None, key=None, opener=urllib.request.urlopen) -> dict:
    url = url or os.environ.get("SENFUND_LLM_URL")
    key = key or os.environ.get("SENFUND_LLM_KEY")
    if not url or not key:
        raise RuntimeError("Invoice drafting is not configured.")
    if not isinstance(text, str) or not 0 < len(text) <= 4000:
        raise ValueError("Paste a message of up to 4000 characters.")
    prompt = ("Extract an invoice from the client message. Reply with only a JSON object with keys "
              "client_name, amount_usd (number), due_date (YYYY-MM-DD), description. Message:\n" + text)
    req = urllib.request.Request(url.rstrip("/") + "/chat/completions", method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        data=json.dumps({"model": os.environ.get("SENFUND_LLM_MODEL", "gpt-4o-mini"),
                         "response_format": {"type": "json_object"},
                         "messages": [{"role": "user", "content": prompt}]}).encode())
    try:
        with opener(req, timeout=15) as r:
            content = json.load(r)["choices"][0]["message"]["content"]
        return validate(json.loads(content))
    except (ValueError, KeyError, IndexError, TypeError):
        raise ValueError("The drafter returned something SenFund could not read. Fill the form by hand.")
    except OSError:
        raise RuntimeError("The drafter is unavailable. Fill the form by hand.")
