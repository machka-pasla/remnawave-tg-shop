import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Tuple, Union, Optional, List
from aiogram import Bot

from config.settings import Settings
from db.dal import promo_code_dal, user_dal
from db.models import PromoCode
from .subscription_service import SubscriptionService
from bot.middlewares.i18n import JsonI18n
from .notification_service import NotificationService


class PromoCodeService:

    # ==============================================================
    # 1) ИНИЦИАЛИЗАТОР — ДОЛЖЕН БЫТЬ ПЕРВЫМ
    # ==============================================================
    def __init__(
        self,
        settings: Settings,
        subscription_service: SubscriptionService,
        bot: Bot,
        i18n: JsonI18n,
    ):
        self.settings = settings
        self.subscription_service = subscription_service
        self.bot = bot
        self.i18n = i18n

    # ==============================================================
    # 2) ПОЛУЧИТЬ ПОСЛЕДНИЙ АКТИВИРОВАННЫЙ СКИДОЧНЫЙ ПРОМОКОД ПОЛЬЗОВАТЕЛЯ
    # ==============================================================

    async def get_active_promo(self, session: AsyncSession, user_id: int) -> Optional[PromoCode]:
        """
        Возвращает последний СКИДОЧНЫЙ промокод пользователя.
        ИСПРАВЛЕНО: убрана ленивя загрузка act.promo_code → ручная выборка.
        """

        # Загружаем все активации
        activations = await promo_code_dal.get_user_promo_activations(session, user_id)
        if not activations:
            return None

        # Перебираем с конца — последний активированный промокод
        for act in reversed(activations):
            promo = await promo_code_dal.get_promo_code_by_id(session, act.promo_code_id)
            if not promo:
                continue

            if not promo.is_active:
                continue

            if promo.bonus_days and promo.bonus_days > 0:
                continue

            if promo.discount_percent or promo.discount_plan_months:
                return promo

        return None

    # ==============================================================
    # 3) ПРИМЕНИТЬ ПРОМОКОД К СТОИМОСТИ ПЛАТЕЖА
    # ==============================================================

    async def apply_promo_to_price(
            self,
            base_price: float,
            months: int,
            promo: Optional[PromoCode],
    ) -> Tuple[float, Optional[PromoCode], Optional[str]]:
        """
        Возвращает:
          new_price,
          promo (если применён), иначе None,
          discount_info_text (строка для описания в платеже)
        """

        if promo is None:
            return base_price, None, None

        has_percent = promo.discount_percent is not None
        has_plan = promo.discount_plan_months is not None

        # ----- 1) Глобальная скидка на все тарифы -----
        if has_percent and not has_plan:
            discount = promo.discount_percent
            new_price = round(base_price * (100 - discount) / 100, 2)
            info = f"-{discount}%"
            return new_price, promo, info

        # ----- 2) Скидка на конкретный тариф (новая модель) -----
        if has_percent and has_plan:
            if promo.discount_plan_months == months:
                discount = promo.discount_percent
                new_price = round(base_price * (100 - discount) / 100, 2)
                info = f"-{discount}% для тарифа {months} мес"
                return new_price, promo, info
            else:
                # Промокод не подходит к выбранному тарифу
                return base_price, None, None

        # ----- 3) LEGACY: скидка только по discount_plan_months, без процента -----
        if not has_percent and has_plan:
            if promo.discount_plan_months == months:
                # Старая логика: фиксированная скидка 20%
                new_price = round(base_price * 0.8, 2)
                info = f"Скидка для тарифа {months} мес (legacy 20%)"
                return new_price, promo, info
            else:
                return base_price, None, None

        # ----- 4) Нет скидочных полей — ничего не делаем -----
        return base_price, None, None

    # ==============================================================
    # 4) ПРИМЕНЕНИЕ ПРОМОКОДА ПОЛЬЗОВАТЕЛЕМ (ввод вручную)
    # ==============================================================

    async def apply_promo_code(
        self,
        session: AsyncSession,
        user_id: int,
        code_input: str,
        user_lang: str,
    ) -> Tuple[bool, Union[str, datetime, dict]]:

        _ = lambda k, **kw: self.i18n.gettext(user_lang, k, **kw)
        code_upper = code_input.strip().upper()

        # 1. Ищем промокод
        promo: Optional[PromoCode] = await promo_code_dal.get_active_promo_code_by_code_str(
            session, code_upper
        )

        if not promo:
            return False, _("promo_code_not_found", code=code_upper)

        # 2. Проверяем, использовал ли пользователь
        existing_activation = await promo_code_dal.get_user_activation_for_promo(
            session, promo.promo_code_id, user_id
        )
        if existing_activation:
            return False, _("promo_code_already_used_by_user", code=code_upper)

        has_bonus = promo.bonus_days is not None and promo.bonus_days > 0
        has_percent = promo.discount_percent is not None
        has_plan = promo.discount_plan_months is not None

        # -------------------------
        # 3. БОНУСНЫЕ ДНИ
        # -------------------------
        if has_bonus:
            new_end_date = await self.subscription_service.extend_active_subscription_days(
                session=session,
                user_id=user_id,
                bonus_days=promo.bonus_days,
                reason=f"promo code {code_upper}",
            )

            if not new_end_date:
                return False, _("error_applying_promo_bonus")

            await promo_code_dal.record_promo_activation(
                session, promo.promo_code_id, user_id, payment_id=None
            )
            await promo_code_dal.increment_promo_code_usage(session, promo.promo_code_id)
            await self._notify_promo_activation(session, user_id, code_upper, promo.bonus_days)

            return True, new_end_date

        # -------------------------
        # 4. СКИДКИ
        # -------------------------

        # 4.1 Глобальная скидка на все тарифы
        if has_percent and not has_plan:
            await promo_code_dal.record_promo_activation(
                session, promo.promo_code_id, user_id, payment_id=None
            )
            await promo_code_dal.increment_promo_code_usage(session, promo.promo_code_id)
            await self._notify_promo_activation(session, user_id, code_upper, None)

            return True, {
                "type": "discount",
                "discount_percent": promo.discount_percent,
                "discount_plan_months": None,
            }

        # 4.2 Скидка на конкретный тариф (новая модель)
        if has_percent and has_plan:
            await promo_code_dal.record_promo_activation(
                session, promo.promo_code_id, user_id, payment_id=None
            )
            await promo_code_dal.increment_promo_code_usage(session, promo.promo_code_id)
            await self._notify_promo_activation(session, user_id, code_upper, None)

            return True, {
                "type": "discount",
                "discount_percent": promo.discount_percent,
                "discount_plan_months": promo.discount_plan_months,
            }

        # 4.3 LEGACY: скидка только по тарифу, без процента (жёсткие 20%)
        if not has_percent and has_plan:
            await promo_code_dal.record_promo_activation(
                session, promo.promo_code_id, user_id, payment_id=None
            )
            await promo_code_dal.increment_promo_code_usage(session, promo.promo_code_id)
            await self._notify_promo_activation(session, user_id, code_upper, None)

            return True, {
                "type": "discount",
                "discount_percent": 20,
                "discount_plan_months": promo.discount_plan_months,
            }

        # -------------------------
        # 5. Ничего не подошло
        # -------------------------
        return False, _("error_applying_promo_bonus")

    async def _notify_promo_activation(
        self,
        session: AsyncSession,
        user_id: int,
        code: str,
        bonus_days: Optional[int]
    ):
        try:
            notification_service = NotificationService(self.bot, self.settings, self.i18n)
            user = await user_dal.get_user_by_id(session, user_id)
            await notification_service.notify_promo_activation(
                user_id=user_id,
                promo_code=code,
                bonus_days=bonus_days,
                username=user.username if user else None
            )
        except Exception as e:
            logging.error(f"Notification send error: {e}")