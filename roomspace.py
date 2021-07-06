#!/usr/bin/env python3

import asyncio
import getpass
from colorama import Fore, Style

from util import add_lib_path

add_lib_path("lib/matrix-nio")
from mnio import AsyncClient, MatrixRoom, RoomGetStateEventError
from mnio.event_builders import AddSpaceChildBuilder
from mnio.responses import RoomGetStateEventResponse



VERBOSE = True

class PlannedSpaceAdd:
    def __init__(self, space, room):
        self.space = space
        self.room = room

class PlannedSpaceRemove:
    def __init__(self, space, room):
        self.space = space
        self.room = room

class SpaceStrategy:
    def get_new_spaces(self, myroomnick, myavatarurl, room, members, previous_spaces):
        return []
    def get_via_for_room(self, room):
        raise NotImplementedError()

async def handle_room(client, room, spaces, strategy, mxid):
    planned_additions = []
    planned_removals = []
    if room.room_type == "m.space" or room.room_type == "org.matrix.msc1772.space":
        # Do not automatically add spaces to spaces
        return [], []
    room_id = room.room_id
    room_name = room.display_name
    myroomnick = room.user_name(mxid)
    myavatarurl = room.avatar_url(mxid)
    member_response = await client.joined_members(room_id = room_id)
    members = member_response.members
    spaces_for_room = await get_space_list_for_room(client, spaces, room)
    if len(spaces_for_room) > 0:
        print(f"{room_name} is in following spaces:")
        for space in spaces_for_room:
            print(f"- {space.display_name}")
    old_spaces_for_room = spaces_for_room.copy()
    new_spaces_for_room = strategy.get_new_spaces(myroomnick, myavatarurl, room, members, old_spaces_for_room)
    for candidate in new_spaces_for_room:
        if isinstance(candidate, str):
            candidate = await get_space_from_list(spaces, candidate)
        if candidate not in old_spaces_for_room:
            planned_additions.append(PlannedSpaceAdd(candidate, room))
    for candidate in old_spaces_for_room:
        if isinstance(candidate, str):
            candidate = await get_space_from_list(spaces, candidate)
        if candidate not in new_spaces_for_room:
            planned_removals.append(PlannedSpaceRemove(candidate, room))
    return planned_additions, planned_removals

async def exec_space_manage(strategy, homeserver, mxid, passwd, script_device_id):
    client = AsyncClient(homeserver, mxid, script_device_id)
    await client.login(passwd)
    print("Fetching rooms...")
    # Sync fetches rooms
    await client.sync()
    # Collect spaces
    spaces = []
    for room in client.rooms.values():
        if room.room_type == "m.space":
            print(f"Found space {room.room_id} {room.display_name}")
            spaces.append(room)
    # Process rooms
    planned_additions = []
    planned_removals = []
    await build_room_space_cache(client, spaces) # TODO
    for room in client.rooms.values():
        pa, pr = await handle_room(client, room, spaces, strategy, mxid)
        planned_additions += pa
        planned_removals += pr

    print("-"*42)
    print("Planned additions:")
    for pa in planned_additions:
        print(f"{pa.room.display_name} -> {pa.space.display_name}")
    for pr in planned_removals:
        print(f"{pr.room.display_name} x {pr.space.display_name}")
    print("-"*42)
    input("Enter to execute")
    for pa in planned_additions:
        await add_room_to_space(client, pa.space, pa.room, strategy.get_via_for_room(pa.room))
    for pa in planned_removals:
        print("WARN: Removing rooms from spaces not implemented yet, skipping")

    await client.logout()
    await client.close()


room_space_cache = dict()

async def build_room_space_cache(client, space_list):
    # TODO update cache on state events
    global room_space_cache
    for space in space_list:
        result = await client.room_get_state(room_id = space.room_id)
        for event in result.events:
            try:
                if event['type'] == "m.space.child":
                    room_id = event['state_key']
                    content = event['content']
                    if content != None:
                        #if VERBOSE: print(f"Room {room_id} is in space {space.room_id}")
                        if room_id in room_space_cache:
                            room_space_cache[room_id].append(space)
                        else:
                            room_space_cache[room_id] = [space]
                    # Some testing code to compare with previous check
                    #legacy = await is_room_in_space(client, space, room_id)
                    #if legacy and content != None:
                    #    print(f"MATCH {room_id} in {space.room_id}")
                    #elif content == None and not legacy:
                    #    print(f"NO MATCH {room_id} in {space.room_id}")
                    #else:
                    #    print(f"OH NOES!!!!! {room_id} in {space.room_id} {legacy} {content}")
            except KeyError as e:
                continue

async def get_space_from_list(space_list, space_id):
    for space in space_list:
        if space_id == space.room_id:
            return space
    raise RuntimeError(f"Did not find space with id {space_id}")

async def get_space_list_for_room(client, all_spaces, room, use_cache=True):
    global room_space_cache
    if use_cache:
        if isinstance(room, str):
            room_id = room
        else:
            room_id = room.room_id
        if room_id in room_space_cache:
            return room_space_cache[room_id]
        else:
            return []
    else:
        result = []
        for space in all_spaces:
            if await is_room_in_space(client, space, room):
                result.append(space)
        return result

async def is_room_in_space(client, space, room):
    if isinstance(space, str):
        space_id = space
    else:
        space_id = space.room_id
    if isinstance(room, str):
        room_id = room
    else:
        room_id = room.room_id
    result = await client.room_get_state_event(
        room_id = space_id,
        event_type = "m.space.child",
        state_key = room_id
    )
    if isinstance(result, RoomGetStateEventResponse):
        if result.content == None:
            #print("Room was removed from space")
            return False
        else:
            #print("Room is in space")
            return True
    else:
        #print("Room is not in space")
        return False

async def add_room_to_space(client, space, room, via_servers):
    if isinstance(space, str):
        space_id = space
    else:
        space_id = space.room_id
    if isinstance(room, str):
        room_id = room
    else:
        room_id = room.room_id
    event_dict = AddSpaceChildBuilder(
            room_id = room_id,
            via_servers = via_servers,
            auto_join = False,
            suggested = False
    ).as_dict()
    await client.room_put_state(
        room_id = space_id,
        event_type = event_dict["type"],
        content = event_dict["content"],
        state_key = event_dict["state_key"]
    )

def space_manage(strategy, homeserver, mxid, passwd, script_device_id = "SCRIPT"):
    asyncio.get_event_loop().run_until_complete(exec_space_manage(strategy, homeserver, mxid, passwd, script_device_id))
