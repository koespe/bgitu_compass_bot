from sqlalchemy import Column
from sqlalchemy import ARRAY, Integer, BigInteger, String
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import declarative_base

from config_reader import engine

Base = declarative_base()


async def db_init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class Users(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True, index=True)
    group_name = Column(String, nullable=True)
    group_id = Column(Integer, nullable=True)
    last_schedule_view = Column(String, default='weekly')
    teacher_name = Column(String, nullable=True)
    favorite_groups = Column(MutableList.as_mutable(ARRAY(Integer)), default=[])
    favorite_teachers = Column(MutableList.as_mutable(ARRAY(String)), default=[])
