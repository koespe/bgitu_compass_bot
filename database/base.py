from contextlib import asynccontextmanager, suppress
from typing import Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, delete, update, case

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
    async def add_user(user_id: Optional[int] = None,
                       group_name: Optional[str] = None,
                       group_id: Optional[int] = None,
                       teacher_name: Optional[str] = None) -> None:
        async with get_session() as session:
            insert_statement = insert(Users).values(
                id=user_id,
                group_name=group_name,
                group_id=group_id,
                teacher_name=teacher_name
            )

            # Если конфликт по PK (id), обновляем остальные поля
            insert_statement = insert_statement.on_conflict_do_update(
                index_elements=[Users.id],  # Указываем колонку, по которой ловим конфликт
                set_=dict(
                    group_name=insert_statement.excluded.group_name,
                    group_id=insert_statement.excluded.group_id
                )
            )

            await session.execute(insert_statement)
            await session.commit()

    @staticmethod
    async def is_user_authorized(user_id: int) -> bool:
        async with get_session() as session:
            query = select(1).where(Users.id == user_id)
            return (await session.scalar(query)) is not None

    @staticmethod
    async def user_data(user_id: int) -> dict:
        async with get_session() as session:
            query = await session.execute(select(Users.group_id,
                                                 Users.group_name,
                                                 Users.last_schedule_view,
                                                 Users.favorite_groups,
                                                 Users.teacher_name
                                                 ).filter(Users.id == user_id))
            user_data = dict(query.one()._mapping)
            return user_data

    @staticmethod
    async def logout(user_id: int) -> None:
        async with get_session() as session:
            with suppress(IntegrityError):
                await session.execute(delete(Users).where(Users.id == user_id))
                await session.commit()

    @staticmethod
    async def change_schedule_view(user_id: int) -> None:
        async with get_session() as session:
            # SQL: UPDATE users SET view = CASE WHEN view = 'weekly' THEN 'daily' ELSE 'weekly' END WHERE id = ...
            stmt = update(Users).where(Users.id == user_id).values(
                last_schedule_view=case(
                    (Users.last_schedule_view == 'weekly', 'daily'),
                    else_='weekly'
                )
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    async def manage_favorites(action: str, user_id: int, group_id: int) -> None:
        async with (get_session() as session):
            query = await session.execute(select(Users).filter(Users.id == user_id))
            user: Users = query.scalar()
            if action == 'add':
                user.favorite_groups.append(group_id)
                user.favorite_groups = list(set(user.favorite_groups))
            elif action == 'delete':
                user.favorite_groups.remove(group_id)
            await session.commit()
