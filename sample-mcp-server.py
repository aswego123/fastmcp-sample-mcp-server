from fastmcp import FastMCP
import random
import datetime

mcp = FastMCP("Local MCP Server")

@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a safe math expression. Example: '2 + 2 * 10'"""
    try:
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expression):
            return "Error: Only basic math operators allowed."
        result = eval(expression, {"__builtins__": {}})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def get_server_time() -> str:
    """Returns the current server date and time."""
    now = datetime.datetime.utcnow()
    return f"Server time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}"

@mcp.tool()
def random_number(min_val: int = 1, max_val: int = 100) -> str:
    """Generate a random number between min_val and max_val."""
    if min_val >= max_val:
        return "Error: min_val must be less than max_val."
    num = random.randint(min_val, max_val)
    return f"Random number between {min_val} and {max_val}: {num}"

@mcp.tool()
def analyze_text(text: str) -> dict:
    """Analyze a given text and return word count, char count, and sentences."""
    words = text.split()
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    return {
        "characters": len(text),
        "words": len(words),
        "sentences": len(sentences),
        "avg_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0
    }

@mcp.tool()
def echo(message: str) -> str:
    """Echo back a message. Useful for testing connectivity."""
    return f"[MCP Server Echo]: {message}"

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000)