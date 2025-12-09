from aiogram import Router

from .payments_crypto import router as crypto_router
from .payments_freekassa import router as freekassa_router
from .payments_platega import router as platega_router
from .payments_severpay import router as severpay_router
from .payments_stars import router as stars_router
from .payments_subscription import router as subscription_selection_router
from .payments_yookassa import router as yookassa_router

router = Router(name="user_subscription_payments_router")

router.include_router(subscription_selection_router)
router.include_router(yookassa_router)
router.include_router(freekassa_router)
router.include_router(platega_router)
router.include_router(severpay_router)
router.include_router(crypto_router)
router.include_router(stars_router)

__all__ = ["router"]
