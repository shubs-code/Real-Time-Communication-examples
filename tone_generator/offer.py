# client.py
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
    kind = "audio"

    def __init__(
        self,
        start_freq=220.0,
        end_freq=880.0,
        duration=5.0,
        samplerate=48000,
        channels=1,
        blocksize=1024,
        amplitude=0.1,
    ):
        super().__init__()
        self.start_freq = start_freq
        self.end_freq = end_freq
        self.duration = duration
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self.amplitude = amplitude

        # state
        self.pts = 0
        self._t = 0.0
        self._phase = 0.0
        self._forward = True  # sweep direction

    async def recv(self):
        """
        Generate one frame of audio.
        """
        await asyncio.sleep(self.blocksize / self.samplerate)  # pacing

        # time array for one frame
        t = (np.arange(self.blocksize) + self._t) / self.samplerate
        self._t += self.blocksize

        # Compute progress along sweep (0 to 1)
        sweep_period = 2 * self.duration  # forward + backward
        sweep_pos = (t % sweep_period) / self.duration

        # Determine sweep direction (ping-pong)
        freq = np.where(
            sweep_pos < 1.0,
            self.start_freq + (self.end_freq - self.start_freq) * sweep_pos,
            self.end_freq - (self.end_freq - self.start_freq) * (sweep_pos - 1.0),
        )

        # Integrate instantaneous frequency to get phase
        phase_increment = 2 * np.pi * freq / self.samplerate
        phase = np.cumsum(phase_increment) + self._phase
        self._phase = phase[-1] % (2 * np.pi)

        # Generate sine wave
        samples = self.amplitude * np.sin(phase)

        # Convert to int16 PCM
        samples_int16 = np.int16(samples * 32767)
        if self.channels == 2:
            samples_int16 = np.repeat(samples_int16[:, np.newaxis], 2, axis=1)

        # Create AudioFrame
        layout = "mono" if self.channels == 1 else "stereo"
        frame = AudioFrame(format="s16", layout=layout, samples=self.blocksize)
        frame.planes[0].update(samples_int16.tobytes())

        frame.sample_rate = self.samplerate
        frame.time_base = fractions.Fraction(1, self.samplerate)
        frame.pts = self.pts
        self.pts += self.blocksize

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
