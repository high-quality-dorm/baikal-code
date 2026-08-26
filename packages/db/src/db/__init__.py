"""db — пакет работы с базой данных университета.

Единственный шлюз к PostgreSQL: доступ (пулы + RLS-контекст), резолюция
identity, валидация SQL, маскирование схемы для LLM, аудит и управление
учётными записями. Приложение не ходит в базу напрямую — только через
фасад `db.gateway.Gateway`.
"""

from db.gateway import Gateway, GatewayError

__all__ = ["Gateway", "GatewayError"]
