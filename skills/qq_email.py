import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .base import BaseSkill

class EmailSkill(BaseSkill):
    def __init__(self, username: str, password: str, imap_server: str = "imap.qq.com"):
        self.username = username
        self.password = password
        self.imap_server = imap_server

    @property
    def name(self) -> str:
        return "email_tool"

    @property
    def description(self) -> str:
        return "Tool for reading, searching, or sending emails"

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
                        "description": "Query email search keyword, e.g., 'express delivery', 'FYP', sender's name, etc."
                    },
                    "to_email": {
                        "type": "string",
                        "description": "Recipient email address when sending email"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Send email subject"
                    },
                    "body": {
                        "type": "string",
                        "description": "Send email body content"
                    }
                },
                "required": ["action"]
            }
        }

    def run(self, params: dict) -> dict:
        action = params.get("action", "search")
        if action == "search":
            keyword = params.get("keyword", "")
            emails = self._search_emails(keyword)
            return {"status": "success", "count": len(emails), "emails": emails}
        elif action == "send":
            to_email = params.get("to_email")
            subject = params.get("subject", "No Subject")
            body = params.get("body", "")
            res = self._send_email(to_email, subject, body)
            return res
        else:
            return {"status": "error", "message": f"Unknown action type: {action}"}

    def _search_emails(self, keyword: str = "") -> list:
        results = []
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, 993)
            mail.login(self.username, self.password)
            mail.select("INBOX")

            status, messages = mail.search(None, 'ALL')
            
            if status != "OK" or not messages[0]:
                return []

            email_ids = messages[0].split()
            recent_ids = email_ids[-15:]

            for e_id in reversed(recent_ids):
                _, msg_data = mail.fetch(e_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Parse subject
                        subject = ""
                        raw_subject = msg.get("Subject", "")
                        if raw_subject:
                            sub_parts = decode_header(raw_subject)
                            for part, encoding in sub_parts:
                                if isinstance(part, bytes):
                                    subject += part.decode(encoding or "utf-8", errors="ignore")
                                else:
                                    subject += part

                        # Parse sender
                        sender = ""
                        raw_sender = msg.get("From", "")
                        if raw_sender:
                            sender_parts = decode_header(raw_sender)
                            for part, encoding in sender_parts:
                                if isinstance(part, bytes):
                                    sender += part.decode(encoding or "utf-8", errors="ignore")
                                else:
                                    sender += part

                        # Keyword filtering
                        if keyword:
                            kw = keyword.lower()
                            if kw not in subject.lower() and kw not in sender.lower():
                                continue  # Skip if not match

                        results.append({
                            "from": sender or raw_sender,
                            "subject": subject or raw_subject,
                            "date": msg.get("Date")
                        })
                        
                        if len(results) >= 5:
                            break
                            
            mail.logout()
            return results
        except Exception as e:
            return [{"error": f"IMAP Search failed: {str(e)}"}]

    def _send_email(self, to_email: str, subject: str, body: str) -> dict:
        try:
            msg = MIMEMultipart()
            msg['From'] = self.username
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            server = smtplib.SMTP_SSL("smtp.qq.com", 465)
            server.login(self.username, self.password)
            server.sendmail(self.username, [to_email], msg.as_string())
            server.quit()
            return {"status": "success", "message": f"Send email successful to {to_email}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send email: {str(e)}"}