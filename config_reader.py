from pydantic import SecretStr, RedisDsn
from pydantic_settings import BaseSettings as PydanticSettings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


class Settings(PydanticSettings):
    bot_token: SecretStr
    db_uri: str  # PostgresDsn это лажа для sqlalchemy
    redis_uri: RedisDsn

    admin_tg_id: int
    api_host: str

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


config = Settings()

engine = create_async_engine(url=config.db_uri)
sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

graphics_id = {
    'start_menu': 'AgACAgIAAxkBAAIE8WXRHpU4o18MXtrPV-JAfevl5l-sAAJM3zEb8M-JSkojjmHebfQvAQADAgADeQADNAQ',
    'group_search': 'AgACAgIAAxkBAAIE-WXRHtyYP_4BJeo8kxAaBkAuH1YtAAJb3zEb8M-JSuAVIGTbK6UMAQADAgADeQADNAQ',

    'schedule': 'AgACAgIAAxkBAAIE-2XRHvjna3eZ8yOfdwj7iSzkVx9NAAJd3zEb8M-JSrG-EA4c-JdEAQADAgADeQADNAQ',
    'settings': 'AgACAgIAAxkBAAIE_WXRHwFmCiJeEzIT2zxRdgixbYVvAAJa3zEb8M-JSh77GYtdAq1nAQADAgADeQADNAQ',
    'notifications': 'AgACAgIAAxkBAAIE_2XRHwMZmZZowIo4MsVntQtRVtKBAAJc3zEb8M-JSqTOkAlB1y1VAQADAgADeQADNAQ',

    'teachers_search': 'AgACAgIAAxkBAAIG4mXg_q70O-hjxCR1sv7NOXkHQTyEAAL11DEbeLUJS1O05KaAI0YrAQADAgADeQADNAQ',
    'teachers_schedule': 'AgACAgIAAxkBAAIG5GXg_r2tbudDvbqHq42A5SJ5VMdcAAL21DEbeLUJS289CLiETFvYAQADAgADeQADNAQ',

    'favorites_main_menu': 'AgACAgIAAxkBAAIHzmX0HwVFct2-vAABBviMT2NlQsOsjgACh9gxG6R5oEs7wfNji6qZWQEAAwIAA3kAAzQE',
    'favorites_search': 'AgACAgIAAxkBAAIH0GX0H5xTWPVgwTEJQLLEesOtV8_HAAKM2DEbpHmgSwIVogbDXULbAQADAgADeQADNAQ',
    'favorites_schedule': 'AgACAgIAAxkBAAIH0mX0H8bdyH1DdhLVuWsM_u9Sx_CSAAKN2DEbpHmgSxn7FlxJXDUlAQADAgADeQADNAQ'
}
