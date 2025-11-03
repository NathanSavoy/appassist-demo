from __future__ import annotations
import os
from typing import Dict, Any, List
from openai import OpenAI

DEFAULT_MODEL = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "You are a resume and cover-letter composer with strict guardrails.\n"
    "• You may ONLY use work-history bullets provided in ALLOWED_BULLETS. Use their text verbatim.\n"
    "• Generate a headline/summary (roughly 10-16 words) and a cover letter in the provided tone, but must not add new factual claims.\n"
    "• The cover letter should reference 1–2 specific experiences by name and attribute them to their source role/company (e.g., 'At FieldCloser…', 'As Event Manager…').\n"
    "• Integrate references naturally into prose (no bullet lists); aim for ~300–450 words.\n"
    "• Optimize for ATS parsing: single column, standard headings, plain bullets.\n"
)



def compose_package(job_description: str, allowed_bullets: List[Dict[str, str]], tone_examples: Dict[str, Any],
                    model: str = DEFAULT_MODEL, target_words: int = 380) -> Dict[str, Any]:
    client = OpenAI()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "JOB_DESCRIPTION:"
                f"\n{job_description}\n\n"
                "ALLOWED_BULLETS: (use verbatim text; refer by id in output)\n"
                + "\n".join(
                    [
                        f"- {b['id']}: {b['text']}"
                        + (
                            f" (from {b.get('meta', {}).get('role')} at {b.get('meta', {}).get('employer')})"
                            if b.get("meta") and (b["meta"].get("role") or b["meta"].get("employer"))
                            else ""
                        )
                        for b in allowed_bullets
                    ]
                )
                + "\n\nROLES (for attribution in the cover letter):\n"
                + "\n".join(
                    sorted(
                        {
                            f"{b.get('meta', {}).get('employer', '')} — {b.get('meta', {}).get('role', '')}"
                            for b in allowed_bullets
                            if b.get("meta")
                        }
                    )
                )
                + "\n\nGUIDANCE FOR COVER LETTER:\n"
                "- Quote or paraphrase 1–2 ALLOWED_BULLETS verbatim and attribute them with their source role/company.\n"
                "- Weave references into natural prose (no lists); keep length ~300–450 words.\n"
                + "\n\nTONE_GUIDE (examples):\n"
                + str(tone_examples)
                + "\n\nReturn JSON with keys: resume.headline, resume.sections[experience], cover_letter{greeting, body_paragraphs[], closing, signature}."
            ),
        },
    ]


    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.4)
    content = resp.choices[0].message.content

    # Best-effort: parse JSON block from the content
    import json, re
    try:
        json_str = re.search(r"\{[\s\S]*\}$", content).group(0)
        data = json.loads(json_str)
        return data
    except Exception:
        # Fallback minimal structure
        return {
            "resume": {
                "headline": "Results-focused builder with AI + product experience.",
                "sections": []
            },
            "cover_letter": {
                "greeting": "Hiring Team",
                "body_paragraphs": ["Thanks for considering my application."],
                "closing": "Sincerely,",
                "signature": ""
            }
        }