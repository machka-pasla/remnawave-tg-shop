from aiogram import Router

from . import create
from . import manage  
from . import bulk

promo_router_aggregate = Router(name="promo_features_router")

promo_router_aggregate.include_router(create.router)
promo_router_aggregate.include_router(manage.router)
promo_router_aggregate.include_router(bulk.router)

__all__ = ("promo_router_aggregate",)