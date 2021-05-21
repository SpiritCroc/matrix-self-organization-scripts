#!/usr/bin/env python3

#
# This example script is supposed to explain how to write own scripts
# that call the renamer.py functionality.
# You can use it as guideline, or write completely different name choice
# strategies that match your use-case.
#

import getpass
from renamer import rename, KeepUnknownStrategy

# Required information
MY_HOMESERVER = "https://example.com:8448"
MY_SERVER_ID = "example.com"
MY_MX_ID = "@sepp:example.com"
SCRIPT_DEVICE_ID = "SELFRENAMER"

# Servers of users that are trusted
PERSONAL_SERVERS = [
    MY_SERVER_ID
]
PERSONAL_CONTACTS = [
    MY_MX_ID,   # Actually unnecessary if MY_SERVER_ID is in PERSONAL_SERVERS
    "@horst:matrix.org",
    "@albert:matrix.org",
    # + automatically include all from PERSONAL_SERVERS
]
# Persons to not consider when they are in a room (e.g. myself and bots)
IGNORE_PERSONS = [
    MY_MX_ID,
    "@mybot:example.com",
    "@someotherbot:matrix.org",
]
# Name to use in rooms where only personal contacts are (except empty rooms)
PERSONAL_DISPLAY_NAME = "Sepp Hans"
PERSONAL_AVATAR = "mxc://example.com/ZathMqeIqiNvFYyOouOBdmKO"
# Default display name
DEFAULT_DISPLAY_NAME = "Mr. S"
PERSONAL_AVATAR = "mxc://example.com/fAfHlbRwCkNcnKUeKnIzBvQq"
# Telegram
TELEGRAM_DISPLAY_NAME = "Sepponator"
TELEGRAM_AVATAR = "mxc://example.com/LqtGpfsrdDVEeJkfqCvGtflM"

# Names not included here are assumed manually set and will not be touched
MANAGED_DISPLAY_NAMES = [
    PERSONAL_DISPLAY_NAME,
    DEFAULT_DISPLAY_NAME,
    TELEGRAM_DISPLAY_NAME,
]
# Same for avatars
MANAGED_AVATARS = [
    PERSONAL_AVATAR,
    DEFAULT_AVATAR,
    TELEGRAM_AVATAR,
]

class SeppStrategy(KeepUnknownStrategy):
    def __init__(self):
        # KeepUnknownStrategy: this strategy will not change display names that have not been added to MANAGED_DISPLAY_NAMES,
        # and avatars not added to MANAGED_AVATARS.
        # If you do not need this restriction, you can inherit from renamer.Strategy directly.
        super().__init__(MANAGED_DISPLAY_NAMES, MANAGED_AVATARS)

    def get_new_name_and_avatar(self, myroomnick, myavatarurl, room, all_members):
        # Implement your own logic here, that chooses a name and avatar for a given room!

        # Filter relevant room members
        members = []
        for member in all_members:
            if member.user_id not in IGNORE_PERSONS:
                members.append(member)

        # Classify the room based on members
        room_is_personal = True
        room_is_telegram = False
        if len(members) == 0:
            # Only ignored persons in here, use default
            print("    Ignore: {} members".format(len(members)))
            return DEFAULT_DISPLAY_NAME, DEFAULT_AVATAR
        else:
            # Check if the contact is personal, bridged, ...
            for member in members:
                member_name = member.display_name
                if " (Telegram)" in member_name:
                    room_is_telegram = True
                member_id = member.user_id
                # Check if the member is on a personal server
                personal_member = False
                for allowed_server in PERSONAL_SERVERS:
                    if member_id.count(":") == 1 and member_id.endswith(":{}".format(allowed_server)):
                        personal_member = True
                        break
                if not personal_member:
                    personal_member = member_id in PERSONAL_CONTACTS
                if VERBOSE:
                    print("    {} {} {}".format("ok" if personal_member else "--", member_name, member_id))
                room_is_personal = room_is_personal and personal_member

        # Now that we have classified the room, select name and avatar
        if room_is_telegram:
            new_name = TELEGRAM_DISPLAY_NAME
            new_avatar = TELEGRAM_AVATAR
        elif room_is_personal:
            new_name = PERSONAL_DISPLAY_NAME
            new_avatar = PERSONAL_AVATAR
        else:
            new_name = DEFAULT_DISPLAY_NAME
            new_avatar = DEFAULT_AVATAR
        return new_name, new_avatar


strategy = SeppStrategy()
passwd = getpass.getpass("Password: ")
rename(strategy, MY_HOMESERVER, MY_MX_ID, passwd, SCRIPT_DEVICE_ID)
