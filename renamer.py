#!/usr/bin/env python3

import asyncio
import getpass
from colorama import Fore, Style
from nio import AsyncClient, MatrixRoom, RoomGetStateEventError


VERBOSE = True

class PlannedRename:
    def __init__(self, room_id, room_name, old_name, new_name, old_avatar, new_avatar):
        self.room_id = room_id
        self.room_name = room_name
        self.old_name = old_name
        self.new_name = new_name
        self.old_avatar = old_avatar
        self.new_avatar = new_avatar

class Strategy:
    def nick_change_allowed(self, myroomnick, myavatarurl):
        return True
    def avatar_change_allowed(self, myroomnick, myavatarurl):
        return True
    def get_new_name_and_avatar(self, myroomnick, myavatarurl, room, members):
        return myroomnick, myavatarurl

class KeepUnknownStrategy(Strategy):
    def __init__(self, known_display_names, known_avatars):
        self.known_display_names = known_display_names
        self.known_avatars = known_avatars
    def nick_change_allowed(self, myroomnick, myavatarurl):
        return myroomnick in self.known_display_names
    def avatar_change_allowed(self, myroomnick, myavatarurl):
        return myavatarurl in self.known_avatars

async def exec_rename(strategy, homeserver, mxid, passwd, script_device_id):
    client = AsyncClient(homeserver, mxid, script_device_id)
    await client.login(passwd)
    print("Fetching rooms...")
    # Sync fetches rooms
    await client.sync()
    planned_renames = []
    for room in client.rooms.values():
        room_id = room.room_id
        myroomnick = room.user_name(mxid)
        myavatarurl = room.avatar_url(mxid)
        nick_change_allowed = strategy.nick_change_allowed(myroomnick, myavatarurl)
        avatar_change_allowed = strategy.avatar_change_allowed(myroomnick, myavatarurl)
        print("ROOM {} {} {}".format(room.display_name, room_id, myroomnick if nick_change_allowed else (Fore.MAGENTA + myroomnick + Style.RESET_ALL)))
        if not nick_change_allowed and not avatar_change_allowed:
            print("  => skip")
            continue
        member_response = await client.joined_members(room_id = room_id)
        members = member_response.members
        new_name, new_avatar = strategy.get_new_name_and_avatar(myroomnick, myavatarurl, room, members)
        if not nick_change_allowed:
            new_name = myroomnick
        if not avatar_change_allowed:
            new_avatar = myavatarurl
        if myroomnick == new_name and myavatarurl == new_avatar:
            print("  => keep {}".format(myroomnick))
        else:
            print(f"  => {Fore.YELLOW}{myroomnick}|{myavatarurl}{Style.RESET_ALL} -> {Fore.CYAN}{new_name}|{new_avatar}{Style.RESET_ALL}")
            planned_renames.append(PlannedRename(room_id=room_id, room_name=room.display_name, old_name=myroomnick, new_name=new_name, old_avatar=myavatarurl, new_avatar=new_avatar))
    # get max room name length only for planned renames for formatting
    max_room_name_len = 0
    for pr in planned_renames:
        max_room_name_len = max(max_room_name_len, len(pr.room_name))
    print("-"*42)
    print("Planned renames:")
    room_format = "{{:<{}}}".format(max_room_name_len)
    for pr in planned_renames:
        room_name = room_format.format(pr.room_name)
        print(f"{room_name} |{pr.old_name}|{pr.old_avatar} -> {pr.new_name}|{pr.new_avatar}")
    print("-"*42)
    input("Enter to rename")
    for pr in planned_renames:
        room_id = pr.room_id
        # Compare https://github.com/matrix-org/matrix-react-sdk/blob/7c4a84aae0b764842fadd38237c1a857437c4f51/src/SlashCommands.tsx#L274
        # https://github.com/matrix-org/matrix-doc/blob/8eb1c531442093d239ab35027d784c4d9cfc8ac9/specification/client_server_api.rst#L1975
        # https://github.com/matrix-org/matrix-doc/blob/9281d0ca13c39b83b8bbba184c8887d3d4faf045/event-schemas/schema/m.room.member
        # https://github.com/matrix-org/matrix-doc/blob/370ae8b9fe873b3ce061e4a8dbd7cf836388d640/event-schemas/examples/m.room.member
        # https://github.com/poljar/matrix-nio/blob/41636f04c14ffede01cf31abc309615b16ac949b/nio/client/async_client.py#L1570
        content = {
            "membership": "join",
            "displayname": pr.new_name,
            "avatar_url": pr.new_avatar
        }
        print(f"{pr.room_name}: {content}")
        result = await client.room_put_state(room_id = room_id, event_type = "m.room.member", content = content, state_key = mxid)
        if VERBOSE:
            print(result)
    await client.logout()
    await client.close()

def rename(strategy, homeserver, mxid, passwd, script_device_id = "SCRIPT"):
    asyncio.get_event_loop().run_until_complete(exec_rename(strategy, homeserver, mxid, passwd, script_device_id))
