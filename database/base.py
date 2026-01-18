from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from config_reader import sessionmaker
from database.models import Users


@asynccontextmanager
async def get_session():
    try:
        async with sessionmaker() as session:
            yield session
    except:
        await session.rollback()
        raise
    finally:
        await session.close()


class DB:
    @staticmethod
    async def add_user(user_id: int, group_name: str, group_id: int) -> None:
        async with get_session() as session:
            user = Users(id=user_id,
                         group_name=group_name,
                         group_id=group_id)
            session.add(user)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                old_user_data_query = select(Users).where(Users.id == user_id)
                old_user_data = await session.scalar(old_user_data_query)
                if old_user_data is not None:
                    await session.delete(old_user_data)
                session.add(user)
                await session.commit()

    @staticmethod
    async def is_user_authorized(user_id: int) -> bool:
        async with get_session() as session:
            resp = (await session.execute(select(Users).filter(Users.id == user_id))).scalar()
        return resp is not None

    @staticmethod
    async def user_data(user_id: int) -> dict:
        async with get_session() as session:
            query = await session.execute(select(Users.group_id,
                                                 Users.group_name,
                                                 Users.last_schedule_view,
                                                 Users.favorite_groups
                                                 ).filter(Users.id == user_id))
            user_data = dict(query.one()._mapping)
            return user_data

    @staticmethod
    async def logout(user_id: int):
        async with get_session() as session:
            query = select(Users).filter(Users.id == user_id)
            user_data = await session.scalar(query)
            try:  # Очень ленивое решение непонятной ошибки алхимии при выборе группы после ошибки 409
                await session.delete(user_data)
                await session.commit()
            except:
                pass

    @staticmethod
    async def change_schedule_view(user_id: int) -> None:
        async with (get_session() as session):
            query = await session.execute(select(Users).filter(Users.id == user_id))
            user = query.scalar()
            user.last_schedule_view = 'daily' if user.last_schedule_view == 'weekly' else 'weekly'
            session.add(user)
            await session.commit()

    @staticmethod
    async def manage_favorites(action: str, user_id: int, group_id: int):
        async with (get_session() as session):
            query = await session.execute(select(Users).filter(Users.id == user_id))
            user: Users = query.scalar()
            if action == 'add':
                user.favorite_groups.append(group_id)
                user.favorite_groups = list(set(user.favorite_groups))
            elif action == 'delete':
                user.favorite_groups.remove(group_id)
            await session.commit()
