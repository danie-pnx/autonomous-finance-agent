import os
import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from groq import AsyncGroq
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from contextlib import AsyncExitStack
import traceback

async def generate_financial_brief() -> str:
    """
    Acts as an MCP Client bridging Groq's LLM reasoning with the remote 
    Railway MCP Server via Server-Sent Events (SSE).
    """
    groq_api_key = os.environ.get("GROQ_API_KEY")
    mcp_url = os.environ.get("RAILWAY_MCP_URL")
    
    if not groq_api_key or not mcp_url:
        raise ValueError("Missing critical environment variables: GROQ_API_KEY or RAILWAY_MCP_URL")
        
    # Initialize the asynchronous Groq client
    client = AsyncGroq(api_key=groq_api_key)
    tickers = ["AAPL", "AMD", "TSLA", "NVDA"]
    
    prompt = f"""
    You are an expert Wall Street Financial Analyst. 
    Use your tools to fetch the latest market sentiment and news headlines for: {', '.join(tickers)}.
    
    Output requirements:
    1. A Markdown table summarizing general sentiment (Bullish/Bearish/Neutral).
    2. A short paragraph for each ticker highlighting critical headlines.
    3. High-utility executive bullet points outlining macro risks or catalysts.
    """

    # We use an AsyncExitStack to safely manage the continuous SSE network stream
    async with AsyncExitStack() as stack:
        # 1. Defensively connect with a timeout
        print(f"Connecting to MCP Server: {mcp_url}")
        try:
            # We add a connection timeout to avoid hanging the Action indefinitely
            transport = await asyncio.wait_for(
                stack.enter_async_context(sse_client(mcp_url)), 
                timeout=15.0
            )
            session = await stack.enter_async_context(ClientSession(*transport))
            await session.initialize()
        except asyncio.TimeoutError:
            raise ConnectionError("Railway MCP server took too long to respond.")
        
        # 2. Fetch the tools dynamically from your Railway server
        mcp_tools = await session.list_tools()
        
        # 3. Translate MCP tool schema into Groq's expected JSON format
        groq_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in mcp_tools.tools]
        
        if response_message.tool_calls:
            messages.append(response_message)
            
            # Use a list to collect results to avoid group-exception interference
            for tool_call in response_message.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments)
                    result = await session.call_tool(tool_call.function.name, arguments=args)
                    
                    # Ensure the tool message includes the EXACT tool_call_id
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id, 
                        "content": result.content[0].text
                    })
                except Exception as e:
                    print(f"Tool execution error: {e}")

        # 4. Initial request to Groq
        messages = [{"role": "user", "content": prompt}]
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
            temperature=0.2
        )
        
        response_message = response.choices[0].message
        
        # 5. Execute tools if Groq decides to use them
        if response_message.tool_calls:
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                # Extract arguments Groq generated
                args = json.loads(tool_call.function.arguments)
                
                # Execute the tool against the Railway server
                result = await session.call_tool(tool_call.function.name, arguments=args)
                
                # Append the raw Yahoo Finance data back into the conversation history
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": result.content[0].text
                })
            
            # 6. Final request to Groq to synthesize the data into the brief
            final_response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.2
            )
            return final_response.choices[0].message.content
        
        return response_message.content

def send_email_report(report_content: str) -> None:
    """Delivers the report payload via Gmail SMTP."""
    sender_email = os.environ.get("MEMBER_EMAIL")
    receiver_email = os.environ.get("MEMBER_EMAIL")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not all([sender_email, app_password]):
        raise ValueError("Missing critical email credentials.")

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "📈 Your Automated Morning Stock Briefing"
    
    msg.attach(MIMEText(report_content, 'plain'))
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())

async def main():
    try:
        print("Initializing cloud-native financial data orchestration pipeline...")
        report = await generate_financial_brief()
        print("Report compiled successfully. Dispatched to delivery sub-routine...")
        send_email_report(report)
        print("Execution lifecycle complete.")
    except Exception:
        traceback.print_exc()
        raise

if __name__ == "__main__":
    # Boot up the asynchronous event loop
    asyncio.run(main())