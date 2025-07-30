import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomOutputOptions,
    WorkerOptions,
    WorkerType,
    cli,
)
from livekit.plugins import bithuman, openai, silero

logger = logging.getLogger("bithuman-livekit-agent")
logger.setLevel(logging.INFO)

load_dotenv()

IMX_MODEL_ROOT = os.getenv("IMX_MODEL_ROOT", "/persistent-storage/imx-models")


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    valid_models = sorted(Path(IMX_MODEL_ROOT).glob("*.imx"))
    if len(valid_models) == 0:
        raise ValueError("No valid models found")

    # example: read model path from participant identity
    remote_participant = await ctx.wait_for_participant()
    if remote_participant.identity in valid_models:
        model_path = valid_models[remote_participant.identity]
        logger.info(f"using model {model_path} from participant identity")
    else:
        model_path = valid_models[0]
        logger.info(f"using default model {model_path}")

    logger.info("staring bithuman runtime")
    bithuman_avatar = bithuman.AvatarSession(
        model_path=str(model_path),
        api_secret=os.getenv("BITHUMAN_API_SECRET"),
        api_token=os.getenv("BITHUMAN_API_TOKEN"),
    )

    # PREREQUISITES FOR LOCAL SETUP ON MACOS:
    # 
    # 1. Install bitHuman's Apple plugin for LiveKit:
    #    pip install https://github.com/bithuman-prod/public-sdk-examples/releases/download/v0.1/bithuman_voice-1.3.2-py3-none-any.whl
    #
    # 2. Configure Apple voices in System Settings:
    #    - Go to System Settings > Accessibility > Spoken Content > System Voice
    #    - Download Siri voices or premium Apple voices 
    #    - See assets/example-select-voice.jpg and assets/example-select-premium-voice.jpg
    #
    # 3. Start bitHuman's Apple TTS/STT services:
    #    bithuman-voice serve --port 8000
    #    (This provides both STT and TTS endpoints at port 8000)
    #
    # 4. Install and run Ollama with a local LLM:
    #    - Install from https://ollama.com/
    #    - Download model: ollama run llama3.2:1b (or llama3.2:3b for better performance)
    #    - Ollama serves on port 11434 by default
    #
    # The configuration below uses these local services for 100% local operation:
    session = AgentSession(
        # STT: Uses bitHuman's Apple Speech Recognition via local service
        stt=openai.STT(
            base_url="http://host.docker.internal:8000/v1", 
            language="en"
        ),
        # LLM: Uses Ollama running locally with Llama 3.2 model
        llm=openai.LLM.with_ollama(
            model="llama3.2:1b",
            base_url="http://host.docker.internal:11434/v1"
        ),
        # TTS: Uses bitHuman's Apple Voices/Siri via local service
        tts=openai.TTS(
            base_url="http://host.docker.internal:8000/v1", 
            voice=""
        ),
        # VAD: Voice Activity Detection using Silero (local)
        vad=silero.VAD.load()
    )

    await bithuman_avatar.start(
        session, 
        room=ctx.room
    )

    await session.start(
        agent=Agent(
            instructions=(
                "Your are helpful assistant, talk to me! Response shortly and concisely."
            )
        ),
        room=ctx.room,
        # audio is forwarded to the avatar, so we disable room audio output
        room_output_options=RoomOutputOptions(audio_enabled=False),
    )

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_type=WorkerType.ROOM,
            job_memory_warn_mb=1500,
            num_idle_processes=1,
            initialize_process_timeout=120,
        )
    )
