from aiogram import Router

from . import start
from .subscription.core import router as subscription_router
from .subscription.payments import router as payments_router
from . import referral
from . import promo_user
from . import trial_handler

user_router_aggregate = Router(name="user_router_aggregate")

user_router_aggregate.include_router(promo_user.router)
user_router_aggregate.include_router(trial_handler.router)
user_router_aggregate.include_router(start.router)

# Подписки
user_router_aggregate.include_router(subscription_router)

# ОПЛАТЫ
user_router_aggregate.include_router(payments_router)

user_router_aggregate.include_router(referral.router)