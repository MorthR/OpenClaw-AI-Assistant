import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .base import BaseSkill

class EmailSkill(BaseSkill):
    def __init__(self):
        pass

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
                        "description": "Query email search keyword, e.g., 'express delivery', 'receipt', sender name, etc. Set to null if no keyword specified."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "The max number of emails to retrieve (e.g. 6 if requested 6 emails). Default is 5."
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
            to_email = params.get("to_email") or params.get("to") or params.get("recipient")
            subject = params.get("subject") or "No Subject"
            body = params.get("body") or params.get("content") or params.get("text") or ""
            if not to_email:
                return {
                    "status": "error",
                    "message": "Failed to send: Recipient email address (to_email) is missing in parameters."
                }

            res = self._send_email(user_email, auth_code, smtp_config[0], smtp_config[1], str(to_email), str(subject), str(body))
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

    def _send_email(self, username: str, auth_code: str, smtp_server: str, port: int, to_email: str, subject: str, body: str) -> dict:
        try:
            to_email = str(to_email or "").strip()
            subject = str(subject or "No Subject").strip()
            body = str(body or "").strip()

            msg = MIMEMultipart()
            msg['From'] = username
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            server = smtplib.SMTP_SSL(smtp_server, port)
            server.login(username, auth_code)
            server.sendmail(username, [to_email], msg.as_string())
            server.quit()
            return {"status": "success", "message": f"Successfully sent email to {to_email}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send email: {str(e)}"}