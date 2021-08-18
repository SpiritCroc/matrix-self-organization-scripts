import asyncio
import inspect
import os
import sys

def add_lib_path(lib_dir):
    lib_dir = os.path.realpath(os.path.abspath(os.path.join(os.path.split(inspect.getfile( inspect.currentframe() ))[0],lib_dir)))
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

async def get_bridges(client, room):
    if isinstance(room, str):
        room_id = room
    else:
        room_id = room.room_id
    result = await client.room_get_state(room_id = room_id)
    bridges = []
    for event in result.events:
        try:
            if event['type'] == "m.bridge" or event['type'] == "uk.half-shot.bridge":
                content = event["content"]
                #bridge_id = content["protocol"]["id"]
                #bridgebot
                bridges.append(content)
        except KeyError as e:
            continue
    return bridges
