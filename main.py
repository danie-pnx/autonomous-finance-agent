import os
import json
import asyncio
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from groq import AsyncGroq
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from contextlib import AsyncExitStack

async def generate_financial_brief() -> str:
    """
    Acts as an MCP Client bridging Groq's LLM reasoning with the remote 
    Railway MCP Server via Server-Sent Events (SSE).
    """
    groq_api_key = os.environ.get("GROQ_API_KEY")
    mcp_url = os.environ.get("RAILWAY_MCP_URL")
    
    if not groq_api_key or not mcp_url:
        raise ValueError("Missing critical environment variables: GROQ_API_KEY or RAILWAY_MCP_URL")
        
    client = AsyncGroq(api_key=groq_api_key)
    tickers = ["AAPL", "AMD", "TSLA", "NVDA"]
    
    prompt = f"""
    You are an expert Wall Street Financial Analyst. 
    Use your tools to fetch the latest market sentiment and news headlines for: {', '.join(tickers)}.
    
    CRITICAL GROUNDING RULES:
    1. You must ONLY use the exact information returned by your tool calls. 
    2. DO NOT use your pre-trained memory, outside knowledge, or make assumptions. (e.g., Do not mention unlisted companies or historical trends not explicitly stated in the tool results).
    3. If the tool data does not contain enough information to formulate a macro risk or catalyst, you must output: "Insufficient data provided for macro analysis." Do not invent one.
    
    Output requirements:
    1. A Markdown table summarizing general sentiment (Bullish/Bearish/Neutral) based strictly on the fetched headlines.
    2. A short paragraph for each ticker highlighting critical headlines from the tool output.
    3. High-utility executive bullet points outlining macro risks or catalysts found ONLY in the provided news.
    """

    async with AsyncExitStack() as stack:
        print(f"Connecting to MCP Server: {mcp_url}")
        try:
            # FIX 1: Actually enforce the 15-second timeout
            transport = await asyncio.wait_for(
                stack.enter_async_context(sse_client(mcp_url)),
                timeout=15.0
            )
            session = await stack.enter_async_context(ClientSession(*transport))
            await session.initialize()
        except asyncio.TimeoutError:
            raise ConnectionError("Railway MCP server took too long to respond.")
        
        mcp_tools = await session.list_tools()
        
        groq_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in mcp_tools.tools]

        # 4. Initial request to Groq
        messages = [{"role": "user", "content": prompt}]
        
        # Swapped to llama-3.3-70b-versatile to clear the 8,000 TPM limit ceiling
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
                try:
                    args = json.loads(tool_call.function.arguments)
                    result = await session.call_tool(tool_call.function.name, arguments=args)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": result.content[0].text
                    })
                except Exception as e:
                    print(f"Tool execution error for {tool_call.function.name}: {e}")
            
            # Final synthesis request using the versatile model
            final_response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.2
            )
            final_message = final_response.choices[0].message

            content = final_message.content
            if not content:
                raise RuntimeError("Groq returned an empty response for the financial brief.")
            return content

        content = response_message.content
        if not content:
            raise RuntimeError("Groq returned an empty response for the financial brief.")
        return content

def send_email_report(report_content: str) -> None:
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

def _print_full_error(error: BaseException, depth: int = 0) -> None:
    indent = "  " * depth
    sub_exceptions = getattr(error, "exceptions", None)

    if sub_exceptions:
        print(f"{indent}{type(error).__name__}: {error} -- unwrapping {len(sub_exceptions)} sub-exception(s):")
        for sub_error in sub_exceptions:
            _print_full_error(sub_error, depth + 1)
    else:
        print(f"{indent}{type(error).__name__}: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)

async def main():
    try:
        print("Initializing cloud-native financial data orchestration pipeline...")
        report = await generate_financial_brief()
        print("Report compiled successfully. Dispatched to delivery sub-routine...")
        send_email_report(report)
        print("Execution lifecycle complete.")
    except Exception as error:
        print("Pipeline Execution Failure:")
        _print_full_error(error)

if __name__ == "__main__":
    asyncio.run(main())