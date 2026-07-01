import pytest
import os
from main import generate_financial_brief, send_email_report

# ----------------------------------------------------------------------
# Tests for generate_financial_brief()
# ----------------------------------------------------------------------

def test_generate_financial_brief_success(mocker):
    """
    Verify that Groq is called with correct parameters and returns data 
    when environment variables are properly defined.
    """
    # Patch environment variables
    mocker.patch.dict(os.environ, {
        "GROQ_API_KEY": "gsk_mock_key_abc123",
        "RAILWAY_MCP_URL": "https://test-mcp.up.railway.app/sse"
    })
    
    # Mock the Groq client object lifecycle
    mock_groq_instance = mocker.MagicMock()
    mock_choice = mocker.MagicMock()
    mock_choice.message.content = "# Mock Financial Report Output"
    mock_groq_instance.chat.completions.create.return_value.choices = [mock_choice]
    
    # Inject mock instance when class initializes
    mocker.patch("main.Groq", return_value=mock_groq_instance)
    
    # Execute routine
    result = generate_financial_brief()
    
    # Assert structural validity
    assert result == "# Mock Financial Report Output"
    mock_groq_instance.chat.completions.create.assert_called_once()
    
    # Verify our custom remote tool configuration metadata was sent correctly
    kwargs = mock_groq_instance.chat.completions.create.call_args[1]
    assert "extra_body" in kwargs
    assert kwargs["extra_body"]["tool_config"]["mcp_servers"][0]["type"] == "sse"

def test_generate_financial_brief_missing_env(mocker):
    """
    Ensure the script raises a ValueError immediately if required API 
    tokens or target URLs are missing from the configuration context.
    """
    mocker.patch.dict(os.environ, {}, clear=True)
    
    with pytest.raises(ValueError) as excinfo:
        generate_financial_brief()
        
    assert "Missing critical environment variables" in str(excinfo.value)


# ----------------------------------------------------------------------
# Tests for send_email_report()
# ----------------------------------------------------------------------

def test_send_email_report_success(mocker):
    """
    Verify that the SMTP subsystem properly authenticates and transfers 
    the email body without throwing errors.
    """
    # Arrange environmental setup
    mocker.patch.dict(os.environ, {
        "MEMBER_EMAIL": "lazycat@example.com",
        "GMAIL_APP_PASSWORD": "abcd-efgh-ijkl-mnop"
    })
    
    # Intercept SMTP context manager initialization
    mock_smtp_class = mocker.patch("smtplib.SMTP_SSL")
    mock_server_context = mock_smtp_class.return_value.__enter__.return_value
    
    # Act
    send_email_report("Test report text content.")
    
    # Assert matching calls on context instances
    mock_server_context.login.assert_called_once_with("lazycat@example.com", "abcd-efgh-ijkl-mnop")
    mock_server_context.sendmail.assert_called_once()
    
    # Extract string payload to ensure headers match expected outcomes
    call_args = mock_server_context.sendmail.call_args[0]
    assert call_args[0] == "lazycat@example.com"
    assert call_args[1] == "lazycat@example.com"
    assert "📈 Your Automated Morning Stock Briefing" in call_args[2]

def test_send_email_report_missing_credentials(mocker):
    """
    Confirm that the program drops processing and raises a ValueError 
    if no user email or app verification credentials are provided.
    """
    mocker.patch.dict(os.environ, {}, clear=True)
    
    with pytest.raises(ValueError) as excinfo:
        send_email_report("Sample Content")
        
    assert "Missing critical email configuration credentials" in str(excinfo.value)