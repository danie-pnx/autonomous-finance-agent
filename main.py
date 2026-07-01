import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from groq import Groq

def generate_financial_brief() -> str:
    """
    Connects to the Groq API and coordinates tool invocation via the 
    remote Railway MCP Server using Server-Sent Events (SSE).
    """
    groq_api_key = os.environ.get("GROQ_API_KEY")
    mcp_url = os.environ.get("RAILWAY_MCP_URL")
    
    if not groq_api_key or not mcp_url:
        raise ValueError("Missing critical environment variables: GROQ_API_KEY or RAILWAY_MCP_URL")
        
    client = Groq(api_key=groq_api_key)
    tickers = ["AAPL", "AMD", "TSLA", "NVDA"]
    
    prompt = f"""
    You are an expert Wall Street Financial Analyst. 
    Use the remote MCP server located at {mcp_url} to fetch the latest market sentiment 
    and news headlines for the following tickers: {', '.join(tickers)}.
    
    Analyze the data and compile a clean, professional Morning Briefing Report.
    Your output must include:
    1. A structured Markdown table summarizing the general sentiment (Bullish/Bearish/Neutral) for each ticker.
    2. A short paragraph for each ticker highlighting the most critical, market-moving news headlines from the past 24 hours.
    3. High-utility executive bullet points outlining macro risks or catalysts.
    """

    # Call Groq utilizing remote Tool configuration primitives
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        extra_body={
            "tool_config": {
                "mcp_servers": [
                    {
                        "url": mcp_url,
                        "type": "sse"
                    }
                ]
            }
        }
    )
    
    return completion.choices[0].message.content

def send_email_report(report_content: str) -> None:
    """
    Establishes a secure SSL connection to Gmail SMTP servers to deliver 
    the generated report payload.
    """
    sender_email = os.environ.get("MEMBER_EMAIL")
    receiver_email = os.environ.get("MEMBER_EMAIL")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not all([sender_email, app_password]):
        raise ValueError("Missing critical email configuration credentials: MEMBER_EMAIL or GMAIL_APP_PASSWORD")

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "📈 Your Automated Morning Stock Briefing"
    
    msg.attach(MIMEText(report_content, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())

if __name__ == "__main__":
    try:
        print("Initializing cloud-native financial data orchestration pipeline...")
        report = generate_financial_brief()
        print("Report compiled successfully. Dispatched to delivery sub-routine...")
        send_email_report(report)
        print("Execution lifecycle complete.")
    except Exception as error:
        print(f"Pipeline Execution Failure: {error}")