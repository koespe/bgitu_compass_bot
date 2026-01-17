import types

from aiogram import Router, F
from aiogram.filters import ChatMemberUpdatedFilter, KICKED, MEMBER
from aiogram.types import ChatMemberUpdated

from database.base import DB

statstics_router = Router()
statstics_router.my_chat_member.filter()
statstics_router.message.filter()




@statstics_router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated):
    try:
        await DB.logout(event.from_user.id)
    except:
        pass


@statstics_router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated):
    pass



# @statstics_router.message(F.text == '/stats_adm')
