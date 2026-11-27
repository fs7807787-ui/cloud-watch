"""用 Gmail 寄通知信（和 ntfy 同時寄出）。

需要兩個 GitHub secret：
- GMAIL_ADDRESS：寄件兼收件的 Gmail 地址
- GMAIL_APP_PASSWORD：這個 Gmail 的應用程式密碼（16 碼）
沒設定時只會印一行訊息，不會讓程式失敗。
"""
import html
import os
import smtplib
import time
from email.message import EmailMessage

ADDR = os.environ.get("GMAIL_ADDRESS", "").strip()
PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
MAIL_TO = os.environ.get("MAIL_TO", "").strip() or ADDR


def send_mail(subject, body, link=None, link_text="打開查看"):
    """寄一封信，成功回傳 True。失敗會重試 2 次，最後失敗只印訊息。"""
    if not (ADDR and PASSWORD and MAIL_TO):
        print("（還沒設定 GMAIL_ADDRESS 或 GMAIL_APP_PASSWORD，這次不寄 email）", flush=True)
        return False
    m = EmailMessage()
    m["Subject"] = subject
    m["From"] = f"價格通知 <{ADDR}>"
    m["To"] = MAIL_TO
    text = body + (f"\n\n{link_text}：{link}" if link else "")
    m.set_content(text)
    lines = "<br>".join(html.escape(x) for x in body.split("\n"))
    btn = (f'<p style="margin-top:16px"><a href="{html.escape(link, quote=True)}" '
           f'style="background:#1a73e8;color:#fff;padding:10px 18px;border-radius:6px;'
           f'text-decoration:none;display:inline-block">{html.escape(link_text)}</a></p>') if link else ""
    m.add_alternative(f'<div style="font-size:15px;line-height:1.6">{lines}</div>{btn}', subtype="html")
    for i in range(3):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
                s.login(ADDR, PASSWORD)
                s.send_message(m)
            print("email 已寄出：", subject, flush=True)
            return True
        except smtplib.SMTPAuthenticationError as e:
            print("email 登入失敗（應用程式密碼或地址不對）：", e.smtp_code, flush=True)
            return False
        except Exception as e:
            print("email 失敗：", repr(e), flush=True)
            time.sleep(5 * (i + 1))
    return False
