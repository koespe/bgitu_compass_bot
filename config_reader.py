import configparser
from pathlib import Path

from aiogram import Bot
from pydantic import SecretStr, RedisDsn
from pydantic_settings import BaseSettings as PydanticSettings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


class Settings(PydanticSettings):
    bot_token: SecretStr
    db_uri: str
    redis_uri: RedisDsn

    admin_tg_id: int
    administration_chat_id: int
    api_host: str

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


config = Settings()

engine = create_async_engine(url=config.db_uri)
sessionmaker = async_sessionmaker(engine, expire_on_commit=False)


class GraphicsConfig:
    def __init__(self):
        self._config = configparser.ConfigParser()
        self.ini_path = Path(__file__).parent / 'images.ini'
        self._config.read(self.ini_path, encoding='utf-8')

        for section in self._config.sections():
            for key, value in self._config.items(section):
                setattr(self, key, value)

    async def validate(self, bot: Bot):
        errors = {}
        if not self.ini_path.exists():
            errors['images.ini'] = 'файл не найден'
        else:
            for section in self._config.sections():
                for key, value in self._config.items(section):
                    if not value:
                        errors[key] = 'пустое значение в images.ini'
                        continue
                    try:
                        await bot.get_file(value)
                    except Exception as e:
                        errors[key] = str(e)

        if errors:
            errors_msg = ('Необходимо настроить графическое оформление бота.\n'
                          'Отправьте фотографии в бота, бот ответит file_id, который нужно '
                          'вставить в файл images.ini\n\n'
                          'Ошибки валидации изображений:\n')

            errors_files = []
            for name, error in errors.items():
                errors_files.append(f"  - {name}: {error}")

            errors_msg += '\n'.join(errors_files)

            await bot.send_message(chat_id=config.admin_tg_id,
                                   text=errors_msg)


graphics = GraphicsConfig()
