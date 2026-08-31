"""
app/core/email_utils.py
-----------------------
Utility functions for sending emails using Python's smtplib.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
import logging

from app.core.config import settings
from app.core.supabase_client import supabase

logger = logging.getLogger(__name__)

async def fetch_all_user_emails() -> list[str]:
    """
    Fetch all registered user emails using Supabase Admin client.
    """
    try:
        # Note: listing users requires service_role key to be set on the client
        # or we can query user_roles and join with public profile if that existed.
        # But `supabase.auth.admin.list_users()` requires service role permissions.
        # We'll use list_users().
        users_resp = supabase.auth.admin.list_users()
        emails = [u.email for u in users_resp if u.email]
        return emails
    except Exception as e:
        logger.error(f"Error fetching user emails: {e}")
        return []

async def send_bulk_email_background(subject: str, html_content: str, recipient_emails: list[str]):
    """
    Send bulk HTML emails in the background.
    """
    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("SMTP credentials not configured. Skipping email blast.")
        return

    def _send_emails():
        try:
            # Connect to SMTP server
            if settings.smtp_port == 465:
                server = smtplib.SMTP_SSL(settings.smtp_server, settings.smtp_port)
            else:
                server = smtplib.SMTP(settings.smtp_server, settings.smtp_port)
                server.starttls()
            
            server.login(settings.smtp_username, settings.smtp_password)
            
            for email_addr in recipient_emails:
                try:
                    msg = MIMEMultipart()
                    msg['From'] = settings.smtp_from_email
                    msg['To'] = email_addr
                    msg['Subject'] = subject
                    
                    msg.attach(MIMEText(html_content, 'html'))
                    server.send_message(msg)
                    logger.info(f"Email sent successfully to {email_addr}")
                except Exception as e:
                    logger.error(f"Failed to send email to {email_addr}: {e}")
                    
            server.quit()
        except Exception as e:
            logger.error(f"SMTP connection error: {e}")

    # Run the blocking SMTP operations in a threadpool
    await asyncio.to_thread(_send_emails)

async def notify_new_course_background(course_title: str):
    emails = await fetch_all_user_emails()
    if not emails:
        return
    html = generate_kahani_email_template(
        title="New Course Available!",
        message=f"A new course <strong>'{course_title}'</strong> has been published on the Kahani Events Training Platform.",
        link=f"{settings.live_platform_url}/courses",
        link_text="View Course"
    )
    await send_bulk_email_background(f"New Course: {course_title}", html, emails)

async def notify_new_video_background(video_title: str, course_id: str):
    emails = await fetch_all_user_emails()
    if not emails:
        return
    html = generate_kahani_email_template(
        title="New Training Video Added!",
        message=f"A new video module <strong>'{video_title}'</strong> has been added. Log in to continue your training.",
        link=f"{settings.live_platform_url}/courses/{course_id}",
        link_text="Watch Video"
    )
    await send_bulk_email_background(f"New Video: {video_title}", html, emails)

def generate_kahani_email_template(title: str, message: str, link: str = "", link_text: str = "View Now") -> str:
    """
    Generate a premium-looking HTML template for Kahani Events emails.
    """
    link_html = ""
    if link:
        link_html = f'''
        <div style="text-align: center; margin-top: 30px;">
            <a href="{link}" style="background-color: #8C345C; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">{link_text}</a>
        </div>
        '''

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #FBF7F0; margin: 0; padding: 40px 0;">
        <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <tr>
                <td style="background-color: #1E544A; padding: 30px; text-align: center;">
                    <h1 style="color: #FBF7F0; margin: 0; font-size: 24px; letter-spacing: 1px;">KAHANI EVENTS</h1>
                    <p style="color: rgba(251, 247, 240, 0.8); margin: 5px 0 0 0; font-size: 14px; text-transform: uppercase;">Internal Training Platform</p>
                </td>
            </tr>
            <tr>
                <td style="padding: 40px;">
                    <h2 style="color: #1E544A; margin-top: 0; font-size: 20px;">{title}</h2>
                    <p style="color: #4A4A4A; line-height: 1.6; font-size: 16px;">
                        {message}
                    </p>
                    {link_html}
                </td>
            </tr>
            <tr>
                <td style="background-color: #F8F5F0; padding: 20px; text-align: center; border-top: 1px solid #E8DDD5;">
                    <p style="color: #888888; margin: 0; font-size: 12px;">
                        This is an automated message from the Kahani Events LMS.
                    </p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
