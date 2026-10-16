from ast import Dict
import os
import re
import sqlite3
import imaplib
import smtplib
import email
from datetime import datetime
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Any
from .base import BaseSkill

class EmailSkill(BaseSkill):
    def __init__(self):
        pass

    @property
    def name(self) -> str:
        return "email_tool"

    @property
    def description(self) -> str:
        return "Tool for reading, searching, or sending emails (supports calendar attachments)"

    @property
    def schema(self) -> dict:
        return {
            "name": "email_tool",
            "description": "Tool for reading, searching, or sending emails",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Operation type: 'search' for searching/reading emails, 'send' for sending emails",
                        "enum": ["search", "send"]
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Query email search keyword."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of emails to retrieve. Default is 5."
                    },
                    "to": {
                        "type": "string",
                        "description": "Recipient email address. If sending to self, use the authenticated user's email address."
                    },
                    "to_email": {
                        "type": "string",
                        "description": "Recipient email address alias."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject"
                    },
                    "body": {
                        "type": "string",
                        "description": "Email content body"
                    },
                    "attachment": {
                        "type": "string",
                        "description": "Attachment filename, e.g., 'calendar_export.ics'"
                    }
                },
                "required": ["action"]
            }
        }

    def _get_servers(self, user_email: str) -> tuple:
        domain = user_email.split("@")[-1].lower() if "@" in user_email else ""
        if "qq.com" in domain:
            return ("imap.qq.com", 993), ("smtp.qq.com", 465)
        elif "163.com" in domain:
            return ("imap.163.com", 993), ("smtp.163.com", 465)
        elif "gmail.com" in domain:
            return ("imap.gmail.com", 993), ("smtp.gmail.com", 465)
        else:
            return (f"imap.{domain}", 993), (f"smtp.{domain}", 465)

    def _generate_ics_bytes(self) -> bytes:
        ics_content = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//OpenClaw AI Personal Agent//EN",
            "X-WR-CALNAME:OpenClaw AI Schedule Export"
        ]

        if os.path.exists("calendar.db"):
            with sqlite3.connect("calendar.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT title, event_date, event_time, category FROM events")
                for title, e_date, e_time, cat in cursor.fetchall():
                    clean_title = re.sub(r'^\s*\[[A-Za-z0-9_-]+\]\s*', '', title).strip()
                    ics_content.append("BEGIN:VEVENT")
                    ics_content.append(f"SUMMARY:[{cat.upper()}] {clean_title}")
                    
                    if e_time in ["All Day"]:
                        ics_content.append(f"DTSTART;VALUE=DATE:{e_date.replace('-', '')}")
                    else:
                        try:
                            dt = datetime.strptime(f"{e_date} {e_time}", "%Y-%m-%d %H:%M")
                            ics_content.append(f"DTSTART:{dt.strftime('%Y%m%dT%H%M%S')}")
                        except Exception:
                            ics_content.append(f"DTSTART;VALUE=DATE:{e_date.replace('-', '')}")
                    ics_content.append("END:VEVENT")

        ics_content.append("END:VCALENDAR")
        return "\r\n".join(ics_content).encode("utf-8")

    def run(self, params: dict, user_credentials: dict = None):
        user_email = user_credentials.get("email") if user_credentials else None
        auth_code = user_credentials.get("auth_code") if user_credentials else None

        if not user_email or not auth_code:
            return {
                "status": "error",
                "message": "Invalid user credentials. Please fill in your email account and authorization code in the settings."
            }

        imap_config, smtp_config = self._get_servers(user_email)
        action = params.get("action", "search")

        if action == "search":
            keyword = params.get("keyword", "")
            limit = int(params.get("limit", 5)) if params.get("limit") else 5
            emails = self._search_emails(user_email, auth_code, imap_config[0], imap_config[1], keyword=keyword, limit=limit)
            return {"status": "success", "count": len(emails), "emails": emails}

        elif action == "send":
            raw_to = params.get("to") or params.get("to_email") or params.get("recipient") or ""
            target_to = str(raw_to).strip().lower()

            if not target_to or "@" not in target_to or target_to in ["me", "self", "myself", "none"]:
                final_recipient = user_email
            else:
                final_recipient = str(raw_to).strip()

            subject = params.get("subject") or "Calendar Export"
            body = params.get("body") or params.get("content") or "Please check the attached calendar file."
            attachment_name = params.get("attachment")
            
            if not attachment_name and ("calendar" in body.lower()):
                attachment_name = "calendar_export.ics"

            res = self._send_email(
                username=user_email,
                auth_code=auth_code,
                smtp_server=smtp_config[0],
                port=smtp_config[1],
                to_email=final_recipient,
                subject=str(subject),
                body=str(body),
                attachment_name=attachment_name
            )
            return res
        else:
            return {"status": "error", "message": f"Unknown action type: {action}"}

    def _search_emails(self, username: str, auth_code: str, imap_server: str, port: int, keyword: str = "", limit: int = 5) -> list:
        results = []
        try:
            mail = imaplib.IMAP4_SSL(imap_server, port)
            mail.login(username, auth_code)
            mail.select("INBOX")

            status, messages = mail.search(None, 'ALL')
            if status != "OK" or not messages[0]:
                return []

            email_ids = messages[0].split()
            fetch_count = max(30, limit * 3)
            recent_ids = email_ids[-fetch_count:]

            for e_id in reversed(recent_ids):
                if len(results) >= limit:
                    break

                _, msg_data = mail.fetch(e_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject = ""
                        raw_subject = msg.get("Subject", "")
                        if raw_subject:
                            sub_parts = decode_header(raw_subject)
                            for part, encoding in sub_parts:
                                if isinstance(part, bytes):
                                    subject += part.decode(encoding or "utf-8", errors="ignore")
                                else:
                                    subject += part
                        sender = ""
                        raw_sender = msg.get("From", "")
                        if raw_sender:
                            sender_parts = decode_header(raw_sender)
                            for part, encoding in sender_parts:
                                if isinstance(part, bytes):
                                    sender += part.decode(encoding or "utf-8", errors="ignore")
                                else:
                                    sender += part
                        if keyword:
                            kw = keyword.lower()
                            if kw not in subject.lower() and kw not in sender.lower():
                                continue

                        results.append({
                            "from": sender or raw_sender,
                            "subject": subject or raw_subject,
                            "date": msg.get("Date")
                        })
                        
            mail.logout()
            return results[:limit]
        except Exception as e:
            return [{"error": f"IMAP Search failed: {str(e)}"}]

    def _send_email(self, username: str, auth_code: str, smtp_server: str, port: int, to_email: str, subject: str, body: str, attachment_name: str = None) -> dict:
        try:
            msg = MIMEMultipart()
            msg['From'] = username
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            if attachment_name and ("ics" in attachment_name.lower() or "calendar" in attachment_name.lower()):
                ics_data = self._generate_ics_bytes()
                part = MIMEApplication(ics_data, Name="calendar_export.ics")
                part['Content-Disposition'] = 'attachment; filename="calendar_export.ics"'
                msg.attach(part)

            server = smtplib.SMTP_SSL(smtp_server, port)
            server.login(username, auth_code)
            server.sendmail(username, [to_email], msg.as_string())
            server.quit()
            return {"status": "success", "message": f"Successfully sent email with schedule export to {to_email}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send email: {str(e)}"}