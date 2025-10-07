import asyncio
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer

async def run():
    # Peer A (the sender) initiates the data channel
    peer_a = RTCPeerConnection(
        configuration=RTCConfiguration(
            iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
        )
    )

    data_channel_a = peer_a.createDataChannel("chat")

    @data_channel_a.on("open")
    def on_open_a():
        print("Peer A data channel opened!")
        data_channel_a.send("Hello from Peer A!")

    @data_channel_a.on("message")
    def on_message_a(message):
        print(f"Peer A received: {message}")

    # Peer B (the receiver) listens for the data channel
    peer_b = RTCPeerConnection(
        configuration=RTCConfiguration(
            iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
        )
    )

    @peer_b.on("datachannel")
    def on_datachannel_b(channel):
        print(f"Peer B data channel opened by remote peer with label: {channel.label}")
        
        @channel.on("open")
        def on_open_b():
            print("Peer B data channel opened!")
            channel.send("Hello from Peer B!")

        @channel.on("message")
        def on_message_b(message):
            print(f"Peer B received: {message}")
            channel.send("Thanks for the message!")

    # --- Signaling exchange (simplified for this example) ---
    offer = await peer_a.createOffer()
    print("Peer A: creating offer...\n\n\n",offer,"\n")
    await peer_a.setLocalDescription(offer)

    await peer_b.setRemoteDescription(peer_a.localDescription)
    answer = await peer_b.createAnswer()
    print("Peer B: setting remote description and creating answer...\n\n\n", answer,"\n")
    await peer_b.setLocalDescription(answer)

    print("Peer A: setting remote description...")
    await peer_a.setRemoteDescription(peer_b.localDescription)

    # Allow time for ICE negotiation and data channels to open
    # print("Waiting for data channels to open and messages to be exchanged...")
    # await asyncio.sleep(10)

    # Clean up
    await peer_a.close()
    await peer_b.close()

if __name__ == "__main__":
    asyncio.run(run())

