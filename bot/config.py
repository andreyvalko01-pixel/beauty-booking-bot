from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = "123456:TEST"
    salon_name: str = "Studio Bloom"
    salon_address: str = "Київ, вул. Ярославів Вал, 15"
    timezone: str = "Europe/Kyiv"

    database_url: str = "sqlite+aiosqlite:///data/salon.sqlite"
    redis_url: str = ""          # якщо задано — стан діалогів зберігається в Redis

    # Telegram ID адміністраторів (через кому)
    admin_ids: str = ""

    # LiqPay: передоплата для послуг дорожче за цю суму
    liqpay_public_key: str = ""
    liqpay_private_key: str = ""
    prepay_from: int = 1000
    prepay_percent: int = 30
    public_url: str = "https://salon.example"   # куди LiqPay шле server_url

    # Google Calendar: JSON сервісного акаунта і календар кожного майстра задається в БД
    google_credentials: str = ""

    slot_minutes: int = 30
    booking_days_ahead: int = 14

    web_admin_user: str = "admin"
    web_admin_password: str = "admin"

    @property
    def admins(self) -> set[int]:
        return {int(x) for x in self.admin_ids.split(",") if x.strip()}


settings = Settings()
