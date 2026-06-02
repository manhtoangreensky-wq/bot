# Telegram Admin Permissions

Use the smallest Telegram permissions required for the bot to serve users.

## Recommended For Private Bot Usage

No group admin permission is required when users interact with TOAN AAS in private chat.

## Recommended If Added To A Group

Allow only what is needed for normal bot replies:

- Read/send messages, if the group workflow requires it.
- Pin messages only if admin deliberately uses pinned notices.

Do not grant:

- Change group info
- Change group photo
- Add new admins
- Ban or restrict members
- Manage video chats
- Manage topics, unless the bot has a specific reviewed feature for that group

## If Telegram Shows A Broad Admin Permission Prompt

Remove the bot from the group and re-add it without broad admin rights. The bot should not need permission to rename the group, change images/descriptions, or alter user/admin permissions.

## Incident Response

If a group title, photo, description, or member/admin permission changes unexpectedly:

1. Remove the bot from the group or revoke admin rights.
2. Check Railway deploy logs for the time window.
3. Check bot source for any Telegram group management API calls.
4. Rotate the Telegram bot token if there is any chance it was exposed.
5. Re-add the bot with minimal permissions only.
