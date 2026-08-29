
from core.agents.assist_agent import AssistAgent
from core.llm import LLMResponse


class _Router:
    def __init__(self, text):
        self.text = text

    def describe(self):
        return {"primary": "stub", "fallback": "stub"}

    async def complete(self, messages, tools=None, temperature=0.2, max_tokens=2048):
        return LLMResponse(text=self.text, model="m", provider="p")


async def test_explain_returns_prose():
    agent = AssistAgent(_Router("This function adds two numbers."))
    r = await agent.run("explain", "calc.py", "def add(a,b):\n    return a+b\n")
    assert r.kind == "prose" and "adds two numbers" in r.text
    assert r.new_content is None


async def test_fix_returns_edit_and_diff():
    fixed = "```python\ndef sub(a, b):\n    return a - b\n```"
    agent = AssistAgent(_Router(fixed))
    r = await agent.run("fix", "calc.py", "def sub(a, b):\n    return a + b\n")
    assert r.kind == "edit"
    assert r.new_content == "def sub(a, b):\n    return a - b\n"
    assert "-    return a + b" in r.diff and "+    return a - b" in r.diff


async def test_no_change_when_identical():
    same = "```\ndef add(a, b):\n    return a + b\n```"
    agent = AssistAgent(_Router(same))
    r = await agent.run("refactor", "calc.py", "def add(a, b):\n    return a + b\n")
    assert r.new_content is None and r.diff == ""


async def test_extract_picks_largest_block():
    text = "here is a note ```\nx\n``` and the file ```\ndef f():\n    return 1\n```"
    agent = AssistAgent(_Router(text))
    r = await agent.run("document", "f.py", "def f():\n    return 0\n")
    assert r.new_content == "def f():\n    return 1\n"
