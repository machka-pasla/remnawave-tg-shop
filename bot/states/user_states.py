from aiogram.fsm.state import State, StatesGroup


class UserPromoStates(StatesGroup):
    waiting_for_promo_code = State()
