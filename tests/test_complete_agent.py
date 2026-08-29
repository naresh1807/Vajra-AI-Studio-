
from core.agents.complete_agent import CompletionAgent
from core.llm import LLMResponse


class _Router:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def describe(self):
        return {"primary": "stub", "fallback": "stub"}

    async def complete(self, messages, tools=None, temperature=0.2, max_tokens=2048):
        self.calls += 1
        return LLMResponse(text=self.text, model="m", provider="p")


async def test_returns_stripped_completion():
    agent = CompletionAgent(_Router("    return a + b\n"))
    out = await agent.complete(prefix="def add(a, b):\n", suffix="", language="python")
    assert out == "    return a + b"


async def test_strips_code_fence():
    agent = CompletionAgent(_Router("```python\nprint('hi')\n```"))
    out = await agent.complete(prefix="def f():\n    ", suffix="", language="python")
    assert out == "print('hi')"


async def test_rejects_leaked_reasoning():
    agent = CompletionAgent(_Router("We need to implement the function. First, handle base cases."))
    out = await agent.complete(prefix="def fib(n):\n    ", suffix="", language="python")
    assert out == ""


async def test_keeps_answer_after_think_tag():
    agent = CompletionAgent(_Router("okay let me think...\n</think>\n    return n * 2"))
    out = await agent.complete(prefix="def double(n):\n", suffix="", language="python")
    assert out.strip() == "return n * 2"


async def test_caps_lines():
    agent = CompletionAgent(_Router("\n".join(f"line{i}" for i in range(20))))
    out = await agent.complete(prefix="x = 1\n", suffix="", language="python")
    assert out.count("\n") <= 5


async def test_caches_identical_context():
    router = _Router("    pass")
    agent = CompletionAgent(router)
    a = await agent.complete(prefix="def g():\n", suffix="", language="python")
    b = await agent.complete(prefix="def g():\n", suffix="", language="python")
    assert a == b and router.calls == 1


async def test_empty_prefix_no_call():
    router = _Router("something")
    agent = CompletionAgent(router)
    out = await agent.complete(prefix="   \n", suffix="", language="python")
    assert out == "" and router.calls == 0
