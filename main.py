#!/usr/bin/env python3
"""
Formiq lead capture server — permanent deployment version.
1. Writes new lead to Notion Leads database via Notion API
2. Sends confirmation email to lead via Gmail SMTP
"""
import json
import os
import smtplib
import urllib.request
import urllib.error
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Config from environment variables ──────────────────────────────────────
NOTION_TOKEN   = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID   = os.environ.get("NOTION_DB_ID", "50a8834a4749445d8185cf6120a74b56")
GMAIL_ADDRESS  = os.environ.get("GMAIL_ADDRESS", "guerreroecommerce1@gmail.com")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")


class LeadSubmission(BaseModel):
    name: str
    email: str
    phone: str = ""
    service: str = "Other"
    message: str = ""


def save_to_notion(lead: LeadSubmission):
    today = date.today().isoformat()
    service_map = {
        "roofing": "Roofing",
        "hvac": "Other",
        "painting": "Painting",
        "remodeling": "Remodeling",
        "concrete": "Concrete",
        "other": "Other",
    }
    service_value = service_map.get(lead.service.lower(), "Other")

    notes_parts = []
    if lead.message:
        notes_parts.append(lead.message)
    notes_parts.append(f"Submitted via Formiq website on {today}")

    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": lead.name}}]},
            "Email": {"email": lead.email},
            "Phone": {"phone_number": lead.phone or None},
            "Service Needed": {"select": {"name": service_value}},
            "Status": {"select": {"name": "New"}},
            "Source": {"select": {"name": "Website"}},
            "Notes": {"rich_text": [{"text": {"content": "\n\n".join(notes_parts)}}]},
            "Date Added": {"date": {"start": today}},
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=data,
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Notion API error {e.code}: {body}")


def send_confirmation_email(lead: LeadSubmission):
    first_name = lead.name.strip().split()[0] if lead.name.strip() else "there"

    plain_body = f"""Hi {first_name},

Got your info. I'll personally reach out within 24 hours.

Here is what happens next:
1. I review what you need
2. I reach out to schedule a quick call
3. We build your system — most go live in 72 hours

Questions in the meantime? Just reply to this email or call me directly.

Anthony Guerrero
Formiq — The system underneath everything.
(508) 374-3530
guerreroecommerce1@gmail.com"""

    html_body = f"""
<div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; color: #1a1710;">
  <div style="background: #080808; padding: 32px 32px 24px; border-radius: 8px 8px 0 0;">
    <p style="font-size: 20px; font-weight: 700; color: #f5a623; margin: 0; letter-spacing: -0.02em;">Formiq</p>
    <p style="font-size: 12px; color: #888580; margin: 4px 0 0; letter-spacing: 0.08em; text-transform: uppercase;">The system underneath everything.</p>
  </div>
  <div style="background: #ffffff; padding: 32px; border: 1px solid #e8e4dc; border-top: none; border-radius: 0 0 8px 8px;">
    <p style="font-size: 16px; margin: 0 0 16px;">Hi {first_name},</p>
    <p style="font-size: 16px; margin: 0 0 24px; color: #333;">Got your info. I'll personally reach out within <strong>24 hours</strong>.</p>
    <p style="font-size: 14px; font-weight: 700; margin: 0 0 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #888;">What happens next</p>
    <ol style="margin: 0 0 24px; padding-left: 20px; font-size: 15px; line-height: 1.8; color: #444;">
      <li>I review what you need</li>
      <li>I reach out to schedule a quick call</li>
      <li>We build your system — most go live in <strong>72 hours</strong></li>
    </ol>
    <p style="font-size: 14px; color: #706c62; margin: 0 0 24px;">Questions? Just reply to this email or call me directly.</p>
    <hr style="border: none; border-top: 1px solid #e8e4dc; margin: 24px 0;" />
    <p style="margin: 0; font-size: 15px; font-weight: 700; color: #1a1710;">Anthony Guerrero</p>
    <p style="margin: 4px 0 0; font-size: 13px; color: #888580;">Formiq &nbsp;·&nbsp; (508) 374-3530 &nbsp;·&nbsp; guerreroecommerce1@gmail.com</p>
  </div>
</div>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Got your info, {first_name} — Anthony from Formiq"
    msg["From"]    = f"Anthony | Formiq <{GMAIL_ADDRESS}>"
    msg["To"]      = lead.email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        smtp.sendmail(GMAIL_ADDRESS, lead.email, msg.as_string())


@app.post("/api/lead", status_code=201)
def submit_lead(lead: LeadSubmission):
    errors = []

    try:
        save_to_notion(lead)
    except Exception as e:
        errors.append(f"Notion: {e}")

    try:
        send_confirmation_email(lead)
    except Exception as e:
        errors.append(f"Email: {e}")

    if len(errors) == 2:
        raise HTTPException(status_code=400, detail=" | ".join(errors))

    return {
        "success": True,
        "notion": "ok" if not any("Notion" in e for e in errors) else "failed",
        "email":  "ok" if not any("Email"  in e for e in errors) else "failed",
    }


@app.get("/api/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
