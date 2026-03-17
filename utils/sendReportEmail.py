"""
Email Report Sender
───────────────────
Sends generated report files (Excel, Image, HTML) to specified recipients
using Gmail SMTP with App Password authentication.

Usage:
    from utils.sendReportEmail import send_report_email

    send_report_email(
        subject="Movie Collection Report",
        body="Please find the attached collection reports.",
        recipients=["user1@gmail.com", "user2@gmail.com"],
        attachments=[
            "reports/Total_States_Report_20260317.xlsx",
            "reports/Total_States_Report_Premium_20260317.png",
            "reports/Total_States_Report_20260317.html",
        ],
    )

Setup:
    1. Set environment variables (or edit EMAIL_CONFIG below):
       - REPORT_EMAIL_SENDER   : Your Gmail address
       - REPORT_EMAIL_PASSWORD : Gmail App Password (NOT your login password)
                                 Generate at: https://myaccount.google.com/apppasswords
       - REPORT_EMAIL_RECIPIENTS: Comma-separated recipient emails

    2. Enable 2-Step Verification on your Google account first,
       then create an App Password for "Mail".
"""

import os
import smtplib
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

# =============================================================================
# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# =============================================================================

EMAIL_CONFIG = {
    "smtp_server":  "smtp.gmail.com",
    "smtp_port":    587,
    "sender_email": os.environ.get("REPORT_EMAIL_SENDER", ""),
    "sender_password": os.environ.get("REPORT_EMAIL_PASSWORD", ""),
    "recipients":   [
        r.strip()
        for r in os.environ.get("REPORT_EMAIL_RECIPIENTS", "").split(",")
        if r.strip()
    ],
}


# =============================================================================
# ── EMAIL SENDER ──────────────────────────────────────────────────────────────
# =============================================================================

def send_report_email(
    subject,
    body,
    recipients=None,
    attachments=None,
    sender_email=None,
    sender_password=None,
    smtp_server=None,
    smtp_port=None,
):
    """
    Send an email with report file attachments.

    Parameters
    ----------
    subject : str
        Email subject line.
    body : str
        Plain-text email body.
    recipients : list[str], optional
        List of recipient email addresses. Falls back to EMAIL_CONFIG.
    attachments : list[str], optional
        List of file paths to attach (Excel, PNG, HTML, etc.).
    sender_email : str, optional
        Sender Gmail address. Falls back to EMAIL_CONFIG / env var.
    sender_password : str, optional
        Sender Gmail App Password. Falls back to EMAIL_CONFIG / env var.
    smtp_server : str, optional
        SMTP server hostname. Defaults to smtp.gmail.com.
    smtp_port : int, optional
        SMTP server port. Defaults to 587 (STARTTLS).

    Returns
    -------
    bool
        True if email sent successfully, False otherwise.
    """
    sender   = sender_email   or EMAIL_CONFIG["sender_email"]
    password = sender_password or EMAIL_CONFIG["sender_password"]
    to_addrs = recipients      or EMAIL_CONFIG["recipients"]
    server   = smtp_server     or EMAIL_CONFIG["smtp_server"]
    port     = smtp_port       or EMAIL_CONFIG["smtp_port"]

    # ── Validate ──────────────────────────────────────────────────────────
    if not sender or not password:
        print("⚠️  [Email] Skipped — no sender credentials configured.")
        print("   Set REPORT_EMAIL_SENDER and REPORT_EMAIL_PASSWORD env vars,")
        print("   or pass sender_email / sender_password to send_report_email().")
        return False

    if not to_addrs:
        print("⚠️  [Email] Skipped — no recipients configured.")
        print("   Set REPORT_EMAIL_RECIPIENTS env var (comma-separated),")
        print("   or pass recipients list to send_report_email().")
        return False

    # ── Build message ─────────────────────────────────────────────────────
    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = ", ".join(to_addrs)
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    # ── Attach files ──────────────────────────────────────────────────────
    attached_count = 0
    for filepath in (attachments or []):
        if not os.path.isfile(filepath):
            print(f"   ⚠️  [Email] Attachment not found, skipping: {filepath}")
            continue

        filename  = os.path.basename(filepath)
        mime_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
        main_type, sub_type = mime_type.split("/", 1)

        with open(filepath, "rb") as f:
            part = MIMEBase(main_type, sub_type)
            part.set_payload(f.read())

        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
        attached_count += 1

    if attached_count == 0 and attachments:
        print("⚠️  [Email] No valid attachments found. Sending email anyway.")

    # ── Send ──────────────────────────────────────────────────────────────
    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(sender, password)
            smtp.sendmail(sender, to_addrs, msg.as_string())

        print(f"📧 [Email] Sent to {len(to_addrs)} recipient(s) with {attached_count} attachment(s).")
        return True

    except smtplib.SMTPAuthenticationError:
        print("❌ [Email] Authentication failed. Check your App Password.")
        print("   Reminder: Use a Gmail App Password, NOT your login password.")
        print("   Generate at: https://myaccount.google.com/apppasswords")
        return False
    except Exception as e:
        print(f"❌ [Email] Failed to send: {e}")
        return False


# =============================================================================
# ── CONVENIENCE WRAPPER ───────────────────────────────────────────────────────
# =============================================================================

def send_collection_report(
    report_type,
    movie_name,
    show_date,
    attachment_paths,
    recipients=None,
    sender_email=None,
    sender_password=None,
):
    """
    Convenience wrapper that builds a nice subject/body and sends the report.

    Parameters
    ----------
    report_type : str
        "states" or "cities" — used in subject line.
    movie_name : str
        Movie name for the subject line.
    show_date : str
        Show date (display format, e.g. "17 Mar 2026").
    attachment_paths : list[str]
        Paths to report files (Excel, PNG, HTML).
    recipients : list[str], optional
        Override default recipients.
    sender_email : str, optional
        Override default sender email.
    sender_password : str, optional
        Override default sender password.
    """
    label   = "States" if report_type == "states" else "Cities"
    now     = datetime.now().strftime("%d %b %Y, %I:%M %p")
    subject = f"{movie_name} — {label} Collection Report ({show_date})"

    # Filter to only existing files
    valid_files = [f for f in attachment_paths if os.path.isfile(f)]
    file_list   = "\n".join(f"  • {os.path.basename(f)}" for f in valid_files)

    body = (
        f"{movie_name} — {label} Collection Report\n"
        f"Show Date: {show_date}\n"
        f"Generated: {now}\n\n"
        f"Attached files:\n{file_list}\n\n"
        f"This is an automated report."
    )

    return send_report_email(
        subject=subject,
        body=body,
        recipients=recipients,
        attachments=valid_files,
        sender_email=sender_email,
        sender_password=sender_password,
    )
