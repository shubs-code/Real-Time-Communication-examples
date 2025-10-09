import asyncio
import aiohttp
import json
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer, MediaStreamTrack

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

SERVER_URL = "http://localhost:8080/offer"

async def run_client():

    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]))

    data_channel = pc.createDataChannel("chat")
    mic_track = LiveAudioTrack()
    pc.addTrack(mic_track)
    
    # player = MediaPlayer("default", format="pulse")
    # player = MediaPlayer("/home/shrubex/Music/music1.mp3")
    # if player.audio:
    #     pc.addTrack(player.audio)
    #     print("✅ Audio track added")    
    
    @data_channel.on("open")
    def on_open():
        print("Peer A data channel opened!")
        data_channel.send("Hello from Peer A!")

    @data_channel.on("message")
    def on_message(message):
        print(f"Peer A received: {message}")


    # Add some event listeners for debugging
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()

    @pc.on("icegatheringstatechange")
    def on_icegatheringstatechange():
        print(f"ICE gathering state is {pc.iceGatheringState}")


    # 2. Create the offer
    print("Creating offer...")
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    print("Offer created and local description set.")

    # 3. Send the offer to the server
    print(f"Sending offer to server at {SERVER_URL}...")
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"offer": pc.localDescription.sdp}
            async with session.post(SERVER_URL, json=payload) as response:
                if response.status == 200:
                    answer_sdp = await response.text()
                    print("Received answer from server.")
                    
                    # 4. Set the remote description with the server's answer
                    answer = RTCSessionDescription(sdp=answer_sdp, type="answer")
                    await pc.setRemoteDescription(answer)
                    print("Remote description set successfully.")
                else:
                    print(f"Error from server: {response.status} - {await response.text()}")
                    await pc.close()
                    return

    except aiohttp.ClientConnectorError as e:
        print(f"Connection Error: Cannot connect to server at {SERVER_URL}. Is the server running?")
        await pc.close()
        return

    # Keep the connection alive to observe state changes
    print("\nConnection handshake complete. Keeping the script alive for 30 seconds.")
    print("Check the 'Connection state' messages to see the connection progress.")
    await asyncio.sleep(15)

    print("\nClosing peer connection.")
    await pc.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("Client stopped by user.")
