import asyncio
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer, MediaStreamTrack
import aiohttp_cors


async def offer(request):

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

    # Set remote description
    try:
        data = await request.json()  # Asynchronously read the JSON data
        offer_sdp = data.get("offer")  # Extract 'offer' from the JSON
        print("\n\n\nOffer SDP,\n", offer_sdp)
        await pc.setRemoteDescription(RTCSessionDescription(offer_sdp, "offer"))
    except Exception as e:
        return web.Response(status=400, text="Invalid JSON data: " + str(e))
    
    
    # Use an event listener to wait for ICE gathering to complete
    gathering_complete = asyncio.Event()
    @pc.on("icegatheringstatechange")
    def on_icegatheringstatechange():
        print(pc.iceGatheringState)
        if pc.iceGatheringState == "complete":
            gathering_complete.set()

    # Create the answer, triggering the ICE gathering
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    try:
        await asyncio.wait_for(gathering_complete.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        print("Warning: ICE gathering timed out. Sending answer anyway.")

    print("\n\n\nAnswer SDP,\n",pc.localDescription.sdp)

    return web.Response(text=pc.localDescription.sdp)

app = web.Application()

cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})

# Add your offer route
app.router.add_post("/offer", offer)

# Enable CORS for all routes
for route in list(app.router.routes()):
    cors.add(route)

if __name__ == "__main__":
    web.run_app(app, port=8080)


