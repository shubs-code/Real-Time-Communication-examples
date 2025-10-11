# client.py
import asyncio
import aiohttp
import json
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer, MediaStreamTrack, MediaRecorder
import requests
import time
import sys

SERVER_URL = "https://rtc-signalling-server-kkhp.vercel.app"
SESSION_ID = None
async def run_client():

    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]))
    data_channel = pc.createDataChannel("chat")
    pc.addTransceiver("audio")
    recorder = MediaRecorder("output.wav", format="wav")  # or "output.wav" if playback not supported

    @pc.on("track")
    async def on_track(track):
        print(f"📡 Received {track.kind} track")

        if track.kind == "audio":
            # Connect incoming audio to recorder
            recorder.addTrack(track)
            await recorder.start()
            print("🎵 Audio playback started")
            # subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "received2.wav"])

        @track.on("ended")
        async def on_ended():
            print("Audio track ended")
            await recorder.stop()

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
    peer2_beat = int(time.time() * 1000)
    payload = {
        "peer2_sdp": f"{pc.localDescription.sdp}",
        "peer2_beat": peer2_beat
    }

    headers = {
        "Content-Type": "application/json"
    }

    url = f"{SERVER_URL}/api/rtc/{SESSION_ID}"

    response = requests.put(url, json=payload, headers=headers)

    # poll for answer from peer 2

    while True:
        try:
            # 🔹 Check current session state
            get_resp = requests.get(url)
            get_resp.raise_for_status()
            rtc_data = get_resp.json()
            
            answer_sdp = rtc_data.get("session").get("peer1_sdp", "")
            print(".", end="", flush=True)
            # If peer1_sdp exists → stop sending updates
            if answer_sdp:
                print("\npeer1_sdp received from client:")
                print(answer_sdp)
                answer = RTCSessionDescription(sdp=answer_sdp, type="answer")
                await pc.setRemoteDescription(answer)
                break

            # Wait 10 seconds before next update
            time.sleep(10)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

    # Keep the connection alive to observe state changes
    print("\nConnection handshake complete. Keeping the script alive for 30 seconds.")
    print("Check the 'Connection state' messages to see the connection progress.")
    await asyncio.sleep(1000)

    print("\nClosing peer connection.")
    await pc.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python offer.py <SESSION_ID>")
        sys.exit(1)
    SESSION_ID = sys.argv[1]
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("Client stopped by user.")
