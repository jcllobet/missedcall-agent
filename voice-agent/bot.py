from pipecat.runner.types import WebSocketRunnerArguments

from missed_call_agent.pipecat_bot import run_twilio_bot


async def bot(runner_args: WebSocketRunnerArguments) -> None:
    await run_twilio_bot(runner_args)
