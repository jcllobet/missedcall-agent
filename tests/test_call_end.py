from types import SimpleNamespace

import pytest
from pipecat.frames.frames import EndTaskFrame, FunctionCallResultProperties, TTSSpeakFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection

from missed_call_agent.pipecat_bot import end_call
from missed_call_agent.prompts import VOICEMAIL_ENDING


class StubLLM:
    def __init__(self) -> None:
        self.frames: list[tuple[object, FrameDirection]] = []

    async def push_frame(self, frame: object, direction: FrameDirection = FrameDirection.DOWNSTREAM):
        self.frames.append((frame, direction))


@pytest.mark.asyncio
async def test_end_call_speaks_final_sentence_and_ends_task() -> None:
    context = LLMContext()
    llm = StubLLM()
    results: list[tuple[dict, FunctionCallResultProperties | None]] = []

    async def result_callback(result, properties=None):
        results.append((result, properties))

    params = SimpleNamespace(
        context=context,
        llm=llm,
        result_callback=result_callback,
    )

    await end_call(params)

    assert context.get_messages() == [{"role": "assistant", "content": VOICEMAIL_ENDING}]
    assert len(llm.frames) == 2

    speak_frame, speak_direction = llm.frames[0]
    assert isinstance(speak_frame, TTSSpeakFrame)
    assert speak_frame.text == VOICEMAIL_ENDING
    assert speak_frame.append_to_context is False
    assert speak_direction == FrameDirection.DOWNSTREAM

    end_frame, end_direction = llm.frames[1]
    assert isinstance(end_frame, EndTaskFrame)
    assert end_direction == FrameDirection.UPSTREAM

    assert results[0][0] == {"status": "ending_call"}
    assert results[0][1].run_llm is False
