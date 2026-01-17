from sqlalchemy import Column, ForeignKey
from sqlalchemy import SmallInteger, ARRAY, Integer, BigInteger, String, Date, Time, Boolean, DateTime
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
    group_name = Column(String)
    group_id = Column(Integer)
    last_schedule_view = Column(String, default='weekly')
    favorite_groups = Column(MutableList.as_mutable(ARRAY(Integer)), default=[])
