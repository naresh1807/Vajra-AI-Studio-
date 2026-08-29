
from core.agents.chat_agent import ChatAgent
from core.llm import ChatMessage, LLMResponse
from core.llm.client import ToolCall
from core.tools import build_default_registry


class _Router:
    """Scripted router: first turn calls a tool, second turn answers."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def describe(self):
        return {"primary": "stub", "fallback": "stub"}

    async def complete(self, messages, tools=None, temperature=0.2, max_tokens=2048):
        resp = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return resp


async def test_plain_answer():
    router = _Router([LLMResponse(text="hello there", model="m", provider="p")])
    agent = ChatAgent(router, build_default_registry())
    turn = await agent.respond([ChatMessage(role="user", content="hi")])
    assert turn.reply == "hello there"
    assert turn.tool_calls == []


async def test_uses_readonly_tool_then_answers(tmp_workspace):
    router = _Router([
        LLMResponse(
            text="",
            model="m",
            provider="p",
            tool_calls=[ToolCall(id="1", name="read_file", arguments={"path": "src/app.py"})],
        ),
        LLMResponse(text="it defines add(a, b)", model="m", provider="p"),
    ])
    agent = ChatAgent(router, build_default_registry())
    turn = await agent.respond(
        [ChatMessage(role="user", content="what does app.py do?")],
        workspace_root=str(tmp_workspace),
    )
    assert "add(a, b)" in turn.reply
    assert turn.tool_calls == [{"tool": "read_file", "arguments": {"path": "src/app.py"}, "success": True}]


async def test_write_tool_refused_in_chat(tmp_workspace):
    router = _Router([
        LLMResponse(
            text="",
            model="m",
            provider="p",
            tool_calls=[ToolCall(id="1", name="write_file", arguments={"path": "x.txt", "content": "no"})],
        ),
        LLMResponse(text="I can't edit from chat; start an autonomous task.", model="m", provider="p"),
    ])
    agent = ChatAgent(router, build_default_registry())
    turn = await agent.respond(
        [ChatMessage(role="user", content="create x.txt")],
        workspace_root=str(tmp_workspace),
    )
    assert not (tmp_workspace / "x.txt").exists()
    assert turn.tool_calls[0]["success"] is False
