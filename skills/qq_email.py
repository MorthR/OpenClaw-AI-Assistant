import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .base import BaseSkill

class EmailSkill(BaseSkill):
    name = "email_tool"
    description = "Personal email operation: search inbox emails by keyword or send new emails to specified addresses"

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.imap_server = "imap.qq.com"
        self.smtp_server = "smtp.qq.com"

    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "Must be 'search' (search emails) or 'send' (send email)"
                },
                "keyword": {
                    "type": "string", 
                    "description": "Keyword for searching emails (if action is 'search')"
                },
                "to_email": {
                    "type": "string", 
                    "description": "Recipient email address (if action is 'send')"
                },
                "subject": {
                    "type": "string", 
                    "description": "Email subject (if action is 'send')"
                },
                "body": {
                    "type": "string", 
                    "description": "Email body (if action is 'send')"
                }
            },
            "required": ["action"]
        }

    def _search_emails(self, keyword: str = "") -> list:
        results = []
        try:
            # Connect to QQ Email IMAP SSL port 993
            mail = imaplib.IMAP4_SSL(self.imap_server, 993)
            mail.login(self.username, self.password)
            mail.select("INBOX")

            search_criterion = f'BODY "{keyword}"' if keyword else 'ALL'
            status, messages = mail.search(None, search_criterion)
            
            if status != "OK" or not messages[0]:
                return []

            email_ids = messages[0].split()
            recent_ids = email_ids[-5:]

            for e_id in reversed(recent_ids):
                _, msg_data = mail.fetch(e_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Parse and decode the subject
                        subject = ""
                        raw_subject = msg.get("Subject", "")
                        if raw_subject:
                            sub_parts = decode_header(raw_subject)
                            for part, encoding in sub_parts:
                                if isinstance(part, bytes):
                                    subject += part.decode(encoding or "utf-8", errors="ignore")
                                else:
                                    subject += part

                        # Parse and decode the sender
                        sender = ""
                        raw_sender = msg.get("From", "")
                        if raw_sender:
                            sender_parts = decode_header(raw_sender)
                            for part, encoding in sender_parts:
                                if isinstance(part, bytes):
                                    sender += part.decode(encoding or "utf-8", errors="ignore")
                                else:
                                    sender += part

                        results.append({
                            "from": sender or raw_sender,
                            "subject": subject or raw_subject,
                            "date": msg.get("Date")
                        })
            mail.logout()
            return results
        except Exception as e:
            return [{"error": f"IMAP search failed: {str(e)}"}]

    def _send_email(self, to_email: str, subject: str, body: str) -> str:
        try:
            msg = MIMEMultipart()
            msg["From"] = self.username
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            # QQ Email SMTP uses SSL port 465
            server = smtplib.SMTP_SSL(self.smtp_server, 465)
            server.login(self.username, self.password)
            server.sendmail(self.username, to_email, msg.as_string())
            server.quit()
            return f"Email sent successfully to {to_email}"
        except Exception as e:
            return f"Failed to send email: {str(e)}"

    def run(self, input_data: dict) -> dict:
        action = input_data.get("action")
        
        if action == "search":
            keyword = input_data.get("keyword", "")
            emails = self._search_emails(keyword)
            return {"status": "success", "action": "search", "count": len(emails), "data": emails}
        
        elif action == "send":
            to_email = input_data.get("to_email")
            subject = input_data.get("subject", "No Subject")
            body = input_data.get("body", "")
            
            if not to_email:
                return {"status": "error", "message": "Missing recipient email address"}
            
            res_msg = self._send_email(to_email, subject, body)
            return {"status": "success", "action": "send", "message": res_msg}
            
        return {"status": "error", "message": f"Unknown operation commandS: {action}"}