from core.llm import ChatMessage, PromptBuilder


def test_prompt_builder_composes_system_and_sections():
    msgs = (
        PromptBuilder("You are Vajra.")
        .add_section("Current workspace", "python project, 3 files")
        .add_section("Empty", "")  # skipped
        .add_section("Relevant code", "def f(): ...")
        .build([ChatMessage(role="user", content="hi")])
    )
    assert msgs[0].role == "system"
    sys = msgs[0].content
    assert sys.startswith("You are Vajra.")
    assert "# Current workspace\npython project, 3 files" in sys
    assert "# Relevant code\ndef f(): ..." in sys
    assert "# Empty" not in sys
    assert msgs[1] == ChatMessage(role="user", content="hi")
