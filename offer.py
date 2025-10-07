# client.py
import asyncio
import aiohttp
import json
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer, MediaStreamTrack

SERVER_URL = "http://localhost:8080/offer"

async def run_client():

    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]))

    data_channel = pc.createDataChannel("chat")
    player = MediaPlayer("/home/shrubex/Music/music1.mp3")
    if player.audio:
        pc.addTrack(player.audio)
        print("✅ Audio track added")
    
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
    await asyncio.sleep(30)

    print("\nClosing peer connection.")
    await pc.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("Client stopped by user.")
