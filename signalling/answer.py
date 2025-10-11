import asyncio
import subprocess
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer, MediaStreamTrack, MediaRecorder
import aiohttp_cors
import requests
import time
import traceback

from av import AudioFrame
import sounddevice as sd
import numpy as np
from queue import Queue, Empty
import fractions

class LiveAudioTrack(MediaStreamTrack):
    """
    A MediaStreamTrack that captures audio from the microphone
    in real-time using sounddevice.
    """

    kind = "audio"

    def __init__(self, samplerate=48000, channels=1, blocksize=512, device=None):
        super().__init__()
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self.queue = Queue()
        self.pts = 0

        if device == None:
            device = sd.default.device[0]
        # Open the microphone stream
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            blocksize=self.blocksize,
            dtype="int16",
            device=device,  # None = default input
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, indata, frames, time, status):
        """
        Called by sounddevice whenever a new chunk of audio is available.
        """
        if status:
            print("Audio stream status:", status)
        self.queue.put(indata.copy())

    async def recv(self):
        """
        Return the next chunk of microphone audio as an AudioFrame.
        """
        # Wait for audio data to arrive
        while True:
            try:
                data = self.queue.get_nowait()
                break
            except Empty:
                await asyncio.sleep(0.001)

        # Convert numpy buffer to AudioFrame
        layout = "mono" if self.channels == 1 else "stereo"
        frame = AudioFrame(format="s16", layout=layout, samples=data.shape[0])
        frame.planes[0].update(data.tobytes())

        frame.sample_rate = self.samplerate
        frame.time_base = fractions.Fraction(1, self.samplerate)
        frame.pts = self.pts
        self.pts += data.shape[0]

        return frame


SERVER_URL = "https://rtc-signalling-server-kkhp.vercel.app"
SESSION_ID = None


async def run_peer(offer_sdp):
    print("function call")
    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])])) 

    @pc.on("datachannel")
    def on_datachannel_b(channel):
        print(f"data channel opened by remote peer with label: {channel.label}")

        @channel.on("open")
        def on_open_b():
            print("Peer B data channel opened!")
            channel.send("Hello from Peer B!")

        @channel.on("message")
        def on_message_b(message):
            print(f"Peer B received: {message}")
            channel.send("Thanks for the message!")

    await pc.setRemoteDescription(RTCSessionDescription(offer_sdp, "offer"))
    
    # Use an event listener to wait for ICE gathering to complete
    gathering_complete = asyncio.Event()
    @pc.on("icegatheringstatechange")
    def on_icegatheringstatechange():
        print(pc.iceGatheringState)
        if pc.iceGatheringState == "complete":
            gathering_complete.set()

    # Create the answer, triggering the ICE gathering
    try:
        mic_track = LiveAudioTrack()
        pc.addTrack(mic_track)
    except Exception as e:
        print("Microphone initialization failed:", e)


    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    try:
        await asyncio.wait_for(gathering_complete.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        print("Warning: ICE gathering timed out. Sending answer anyway.")

    print("\n\n\nAnswer SDP,\n",pc.localDescription.sdp)

    payload = {
        "peer1_sdp": f"{pc.localDescription.sdp}",
        "peer1_beat" : int(time.time() * 1000)
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.put(f"{SERVER_URL}/api/rtc/{SESSION_ID}", json=payload, headers=headers)

    print("Status Code:", response.status_code)
    await asyncio.sleep(1000)


def session_setup():
    response = requests.get(f"{SERVER_URL}/api/session")
    if response.status_code == 200:
        data = response.json()
        global SESSION_ID
        SESSION_ID = data.get("session_id")
        print("Session ID:", SESSION_ID)
        while True:
            try:
                rtc_resp = requests.get(f"{SERVER_URL}/api/rtc/{SESSION_ID}")
                rtc_resp.raise_for_status()
                rtc_data = rtc_resp.json()

                peer2_sdp = rtc_data.get("session").get("peer2_sdp", "")
                print(".", end="", flush=True)
                if peer2_sdp:
                    print("\n peer2_sdp received:")
                    print(peer2_sdp)
                    asyncio.run(run_peer(peer2_sdp))
                    break

                # Wait before checking again
                time.sleep(10)

            except Exception as e:
                print("Error while polling:", e)
                traceback.print_exc()
                time.sleep(5)
    else:
        print("Error:", response.status_code, response.text)

if __name__ == "__main__":
    session_setup()

