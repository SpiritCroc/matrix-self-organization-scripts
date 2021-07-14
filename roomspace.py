#!/usr/bin/env python3

import asyncio
import getpass
from colorama import Fore, Style

from .util import add_lib_path

add_lib_path("lib/matrix-nio")
from mnio import AsyncClient, MatrixRoom, RoomGetStateEventError
from mnio.event_builders import AddSpaceChildBuilder, RemoveSpaceChildBuilder
from mnio.responses import RoomGetStateEventResponse
from mnio import RoomMemberEvent, SpaceChildEvent



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

class RoomSpaceController:
    def __init__(self, strategy, homeserver, mxid, passwd, script_device_id):
        self.strategy = strategy
        self.homeserver = homeserver
        self.mxid = mxid
        self.passwd = passwd
        self.script_device_id = script_device_id
        self.client = None
        self.room_space_cache = dict()
        self.spaces_cache = []

    async def handle_room(self, room):
        planned_additions = []
        planned_removals = []
        if room.room_type == "m.space" or room.room_type == "org.matrix.msc1772.space":
            # Do not automatically add spaces to spaces
            return [], []
        room_id = room.room_id
        room_name = room.display_name
        myroomnick = room.user_name(self.mxid)
        myavatarurl = room.avatar_url(self.mxid)
        member_response = await self.client.joined_members(room_id = room_id)
        members = member_response.members
        spaces_for_room = await self.get_space_list_for_room(room)
        if len(spaces_for_room) > 0:
            print(f"{room_name} is in following spaces:")
            for space in spaces_for_room:
                print(f"- {space.display_name}")
        else:
            print(f"{room_name} is in no spaces.")
        old_spaces_for_room = spaces_for_room.copy()
        new_spaces_for_room = self.strategy.get_new_spaces(myroomnick, myavatarurl, room, members, old_spaces_for_room)
        # For comparison what changed, use room ids
        old_spaces_for_room = [space.room_id for space in spaces_for_room]
        new_spaces_for_room = [space if isinstance(space, str) else space.room_id for space in new_spaces_for_room]
        for candidate in new_spaces_for_room:
            if candidate not in old_spaces_for_room:
                candidate = await self.get_space_from_id(candidate)
                planned_additions.append(PlannedSpaceAdd(candidate, room))
        for candidate in old_spaces_for_room:
            if candidate not in new_spaces_for_room:
                candidate = await self.get_space_from_id(candidate)
                planned_removals.append(PlannedSpaceRemove(candidate, room))
        return planned_additions, planned_removals

    async def print_planned_changes(self, planned_additions, planned_removals):
        print("Planned additions:")
        for pa in planned_additions:
            print(f"{pa.room.display_name} -> {pa.space.display_name}")
        print("Planned removals:")
        for pr in planned_removals:
            print(f"{pr.room.display_name} x {pr.space.display_name}")

    async def exec_planned_changes(self, planned_additions, planned_removals):
            for pa in planned_additions:
                await self.add_room_to_space(pa.space, pa.room, self.strategy.get_via_for_room(pa.room))
            for pa in planned_removals:
                await self.remove_room_from_space(pa.space, pa.room)

    async def exec_space_manage(self):
        self.client = AsyncClient(self.homeserver, self.mxid, self.script_device_id)
        await self.client.login(self.passwd)
        print("Fetching rooms...")
        # Sync fetches rooms
        await self.client.sync()
        # Collect and categorize spaces and rooms
        await self.build_room_space_cache()
        # Process rooms
        planned_additions = []
        planned_removals = []

        if True: # TODO parameter
            print("Doing initial space management for all rooms...")
            for room in self.client.rooms.values():
                pa, pr = await self.handle_room(room)
                planned_additions += pa
                planned_removals += pr

            print("-"*42)
            await self.print_planned_changes(planned_additions, planned_removals)
            print("-"*42)
            input("Enter to execute")
            await self.exec_planned_changes(planned_additions, planned_removals)

        if True: # TODO parameter
            print("Start listening to room/space changes to update affected rooms only...")
            # Listen to room member events: these are sent on room joins, and some spaces might depend on joined members as well,
            # so recategorize rooms on member events.
            self.client.add_event_callback(self.handle_room_update, (RoomMemberEvent,))
            # We need to update our room/space cache on space changes. Also, we want to do a room update after that as well.
            self.client.add_event_callback(self.handle_space_update, (SpaceChildEvent,))
            await self.client.sync_forever(timeout=30000, full_state=True)

        await self.client.logout()
        await self.client.close()

    async def get_room_list_for_space(self, space):
        room_list = []
        result = await self.client.room_get_state(room_id = space.room_id)
        for event in result.events:
            try:
                if event['type'] == "m.space.child":
                    room_id = event['state_key']
                    content = event['content']
                    if content != None and len(content) > 0:
                        room_list.append(room_id)
                        #if VERBOSE: print(f"Room {room_id} is in space {space.room_id}")
                    # Some testing code to compare with previous check
                    #legacy = await self.is_room_in_space(self.client, space, room_id)
                    #if legacy and content != None:
                    #    print(f"MATCH {room_id} in {space.room_id}")
                    #elif content == None and not legacy:
                    #    print(f"NO MATCH {room_id} in {space.room_id}")
                    #else:
                    #    print(f"OH NOES!!!!! {room_id} in {space.room_id} {legacy} {content}")
            except KeyError as e:
                continue
        return room_list

    async def build_room_space_cache(self):
        # Also build spaces cache
        self.spaces_cache = []
        for room in self.client.rooms.values():
            if room.room_type == "m.space":
                print(f"Found space {room.room_id} {room.display_name}")
                self.spaces_cache.append(room)
        # Rooms in selected spaces
        for space in self.spaces_cache:
            room_list = await self.get_room_list_for_space(space)
            for room_id in room_list:
                if room_id in self.room_space_cache:
                    self.room_space_cache[room_id].append(space)
                else:
                    self.room_space_cache[room_id] = [space]

    async def handle_room_update(self, room, event):
        if room.room_type == "m.space" and room not in self.spaces_cache:
            print(f"NEW SPACE {room}")
            self.spaces_cache.append(room)
        print(f"ROOM EVENT {event}")
        planned_additions, planned_removals = await self.handle_room(room)
        print("-"*42)
        await self.print_planned_changes(planned_additions, planned_removals)
        print("-"*42)
        await self.exec_planned_changes(planned_additions, planned_removals)

    async def handle_space_update(self, space, event):
        print(f"SPACE EVENT {event}") # TODO try catch
        # Update cache
        room_id = event.state_key
        content = event.content
        print(f"{content}") # TODO
        if content != None and len(content) > 0:
            # room_id added to space
            if room_id in self.room_space_cache:
                if space not in self.room_space_cache[room_id]:
                    self.room_space_cache[room_id].append(space)
            else:
                self.room_space_cache[room_id] = [space]
        else:
            # room_id removed from space
            if room_id in self.room_space_cache:
                if space in self.room_space_cache[room_id]:
                    self.room_space_cache[room_id].remove(space)
        # Handle_room update for child
        try:
            room = self.client.rooms[room_id]
            await self.handle_room_update(room, event)
        except KeyError:
            print(f"Room {event.state_key} not found")

    async def get_space_from_id(self, space_id):
        for space in self.spaces_cache:
            if space_id == space.room_id:
                return space
        raise RuntimeError(f"Did not find space with id {space_id}")

    async def get_space_list_for_room(self, room, use_cache=True):
        if use_cache:
            if isinstance(room, str):
                room_id = room
            else:
                room_id = room.room_id
            if room_id in self.room_space_cache:
                return self.room_space_cache[room_id]
            else:
                return []
        else:
            result = []
            for space in self.spaces_cache:
                if await self.is_room_in_space(space, room):
                    result.append(space)
            return result

    async def is_room_in_space(self, space, room):
        if isinstance(space, str):
            space_id = space
        else:
            space_id = space.room_id
        if isinstance(room, str):
            room_id = room
        else:
            room_id = room.room_id
        result = await self.client.room_get_state_event(
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

    async def add_room_to_space(self, space, room, via_servers):
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
        await self.client.room_put_state(
            room_id = space_id,
            event_type = event_dict["type"],
            content = event_dict["content"],
            state_key = event_dict["state_key"]
        )

    async def remove_room_from_space(self, space, room):
        if isinstance(space, str):
            space_id = space
        else:
            space_id = space.room_id
        if isinstance(room, str):
            room_id = room
        else:
            room_id = room.room_id
        event_dict = RemoveSpaceChildBuilder(
                room_id = room_id,
        ).as_dict()
        await self.client.room_put_state(
            room_id = space_id,
            event_type = event_dict["type"],
            content = event_dict["content"],
            state_key = event_dict["state_key"]
        )

def space_manage(strategy, homeserver, mxid, passwd, script_device_id = "SCRIPT"):
    rsc = RoomSpaceController(strategy, homeserver, mxid, passwd, script_device_id)
    asyncio.get_event_loop().run_until_complete(rsc.exec_space_manage())
