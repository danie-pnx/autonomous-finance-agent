# Automated Stock News & Sentiment Aggregator System: Orchestrator Scripts & Scheduler Script as MCP Client.

## Abstract

This project implements an automated stock market intelligence pipeline that aggregates and summarizes financial information for a watchlist of technology stocks (e.g., `AAPL`, `AMD`, `TSLA`, `NVDA`). 

Using the [main.py](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/main.py) as orchestrator, the system:
1. Connects to a Model Context Protocol (MCP) server over SSE to dynamically discover and query real-time market data tools.
2. Leverages the `llama-3.3-70b-versatile` model via Groq API to compile a factually grounded financial briefing using the retrieved tool outputs.
3. Automatically dispatches the compiled brief as an email report.

The entire process is automated as a scheduled workflow running Monday through Friday mornings via GitHub Actions, as defined in [.github/workflows/schedule_brief.yml](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/.github/workflows/schedule_brief.yml).

> Related Repository : [MCP Server Script](https://github.com/danie-pnx/stock-mcp-server).

## Tech Stack

The orchestrator and automated scheduler are built with:
- **Python**: `3.14.4` (Runtime environment)
- **Groq**: `1.5.0` (Client SDK for calling the Llama inference endpoints)
- **mcp**: `1.28.1` (Model Context Protocol client library)

See [requirements.txt](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/requirements.txt) for the direct package dependencies.

## How The System Works

### Financial Briefing Generation

The core analysis pipeline is implemented in the [generate_financial_brief](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/main.py#L13) function within [main.py](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/main.py). The pipeline consists of the following 5 phases:

1. **Initialization and Prompt Setup:**
   Reads API credentials and connection configuration from the environment, starts an `AsyncGroq` client instance, defines the watchlist (`AAPL`, `AMD`, `TSLA`, `NVDA`), and structures the system prompt with strict grounding constraints to prevent model hallucinations.
2. **Connect to MCP Server:**
   Establishes a connection to the Model Context Protocol (MCP) server over SSE using the client session transport.
3. **Discovery & Mapping Tool:**
   Queries the list of available market tools from the server and dynamically adapts them to JSON schemas matching the requirements for LLM function calling.
4. **Interactive Tool Calling Loop:**
   Queries the model, executes any requested stock/sentiment tool calls on the server, collects the tool outputs, updates the message thread context, and gets the final brief from the model.
5. **Final Brief Retrieval:**
   Extracts and parses the finished brief content (or reasoning process), checks that it is non-empty, and returns it.

### Email Generation and Delivery

The compiled briefing report is dispatched via email through the [send_email_report](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/main.py#L116) function. This process consists of the following 3 parts:

1. **Initialization:**
   Loads the email credentials (`MEMBER_EMAIL` and `GMAIL_APP_PASSWORD`) from the environment and ensures both required fields are present.
2. **Create Email:**
   Constructs a `MIMEMultipart` email message, setting the sender, receiver, and subject line ("The Automated Morning Stock Briefing"), and attaches the brief text as plain text.
3. **Send the Email via SMTP:**
   Connects securely to `smtp.gmail.com` on port `465` using SSL, performs the login handshake, sends the generated email payload to the recipient, and closes the connection.

### Automated Schedule and Execution

The pipeline automation is managed by the GitHub Actions workflow defined in [.github/workflows/schedule_brief.yml](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/.github/workflows/schedule_brief.yml). The workflow consists of the following 3 parts:

1. **The Automated Trigger (Cron Schedule):**
   Runs automatically via a cron trigger (`30 7 * * 0-4`) at 07:30 UTC from Sunday to Thursday to deliver the briefings on Monday through Friday mornings.
2. **The Manual Trigger (Workflow Dispatch):**
   Allows manual triggers via `workflow_dispatch` directly from the GitHub Actions user interface for immediate testing.
3. **The Execution Runner and Steps:**
   Uses an `ubuntu-latest` runner with Python `3.14`, checks out the source code, installs dependencies from [requirements.txt](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/requirements.txt), binds credentials from GitHub secrets, and runs [main.py](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/main.py).

## How to setup

1. Clone this repository and the [MCP Server Script](https://github.com/danie-pnx/stock-mcp-server) repository.
2. Deploy the MCP server from the [MCP Server Script](https://github.com/danie-pnx/stock-mcp-server) repository (e.g., to Railway).
3. Add the required environment variables to your GitHub Secrets and Variables following the pattern defined in [example.env](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/example.env):
   - `GROQ_API_KEY`: Your Groq API key.
   - `RAILWAY_MCP_URL`: The endpoint URL of your deployed SSE MCP server.
   - `MEMBER_EMAIL`: The target email for the stock briefing report.
   - `GMAIL_APP_PASSWORD`: The 16-character Gmail App Password for SMTP authentication.
4. Customize settings as needed:
   - Edit the cron timing schedule in [.github/workflows/schedule_brief.yml](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/.github/workflows/schedule_brief.yml).
   - Edit the target model, ticker watchlist, and system prompt in [main.py](https://github.com/danie-pnx/autonomous-finance-agent/blob/main/main.py).

   > [!NOTE]
   > Different models may require different configurations or API keys depending on the client SDK.
5. Run the workflow in GitHub Actions (either manually using `workflow_dispatch` or waiting for the cron trigger).