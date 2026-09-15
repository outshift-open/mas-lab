def translate_mcp_error(error: Exception) -> Dict[str, Any]:
    """Translates an MCP/SDK error into a mas-lab compatible error dict."""
    return {
        "status": "error",
        "error": str(error),
        "type": error.__class__.__name__
    }

def wrap_mcp_result(result: Any) -> Dict[str, Any]:
    """Wraps an MCP tool result into a mas-lab result dict."""
    # MCP results often have 'content' with 'text'
    if isinstance(result, dict) and "content" in result:
        # Extract text content if available
        text_content = ""
        for item in result["content"]:
            if item.get("type") == "text":
                text_content += item.get("text", "")
        return {"result": text_content}
    
    return {"result": result}
