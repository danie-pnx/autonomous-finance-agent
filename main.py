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
            transport = await stack.enter_async_context(
                sse_client(mcp_url)
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

        # 4. Initial request to Groq
        # reasoning_format="hidden" keeps gpt-oss's chain-of-thought out of the
        # response entirely, so .content always holds the final answer rather
        # than the model sometimes putting the real output in .reasoning instead.
        messages = [{"role": "user", "content": prompt}]
        response = await client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
            temperature=0.2,
            reasoning_format="hidden"
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
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.2,
                reasoning_format="hidden"
            )
            final_message = final_response.choices[0].message

            # Defensive fallback: even with reasoning_format="hidden", gpt-oss
            # models on Groq have occasionally been reported to leave .content
            # empty while the real answer lands in .reasoning instead. Rather
            # than silently emailing an empty report, fall back to whichever
            # field actually has text, and fail loudly if neither does.
            content = final_message.content or getattr(final_message, "reasoning", None)
            if not content:
                raise RuntimeError(
                    "Groq returned an empty response for the financial brief "
                    "(both .content and .reasoning were empty)."
                )
            return content

        content = response_message.content or getattr(response_message, "reasoning", None)
        if not content:
            raise RuntimeError(
                "Groq returned an empty response for the financial brief "
                "(both .content and .reasoning were empty)."
            )
        return content

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

def _print_full_error(error: BaseException, depth: int = 0) -> None:
    """
    Recursively prints every underlying exception and its traceback.

    asyncio/anyio TaskGroups (used internally by the mcp SSE client) wrap
    real errors in an ExceptionGroup, whose default str() is a useless
    "unhandled errors in a TaskGroup (N sub-exceptions)". This walks the
    .exceptions attribute (present on ExceptionGroup/BaseExceptionGroup)
    to surface what actually went wrong, at every nesting level.
    """
    indent = "  " * depth
    sub_exceptions = getattr(error, "exceptions", None)

    if sub_exceptions:
        print(f"{indent}{type(error).__name__}: {error} -- unwrapping {len(sub_exceptions)} sub-exception(s):")
        for sub_error in sub_exceptions:
            _print_full_error(sub_error, depth + 1)
    else:
        print(f"{indent}{type(error).__name__}: {error}")
        # Full traceback for the innermost, actionable exception.
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
    # Boot up the asynchronous event loop
    asyncio.run(main())