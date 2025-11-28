from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    # --- Broadcast ---
    waiting_for_broadcast_message = State()
    confirming_broadcast = State()

    # --- Promo (Existing) ---
    waiting_for_promo_details = State()
    waiting_for_promo_code = State()
    waiting_for_promo_bonus_days = State()
    waiting_for_promo_max_activations = State()
    waiting_for_promo_validity_days = State()

    waiting_for_promo_edit_details = State()
    waiting_for_promo_edit_code = State()
    waiting_for_promo_edit_bonus_days = State()
    waiting_for_promo_edit_max_activations = State()
    waiting_for_promo_edit_validity_days = State()

    waiting_for_bulk_promo_quantity = State()
    waiting_for_bulk_promo_bonus_days = State()
    waiting_for_bulk_promo_max_activations = State()
    waiting_for_bulk_promo_validity_days = State()

    # --- NEW: Promo Discount States ---
    # одиночный промо (новая логика)
    waiting_for_promo_type = State()               # бонус / скидка на все / скидка на тариф
    waiting_for_promo_discount_percent = State()   # ввод процента скидки
    waiting_for_promo_plan_months = State()        # ввод количества месяцев (1/3/6/12)

    # массовое создание промо (новая логика)
    waiting_for_bulk_promo_type = State()              # тип промокода при массовом создании
    waiting_for_bulk_promo_discount_percent = State()  # процент скидки для массовых
    waiting_for_bulk_promo_plan_months = State()       # на какой тариф действует (если нужно)

    # --- User management ---
    waiting_for_user_id_to_ban = State()
    waiting_for_user_id_to_unban = State()
    waiting_for_user_id_for_logs = State()
    waiting_for_user_search = State()
    waiting_for_subscription_days_to_add = State()
    waiting_for_direct_message_to_user = State()
    waiting_for_user_delete_confirmation = State()

    # --- Ads campaigns ---
    waiting_for_ad_source = State()
    waiting_for_ad_start_param = State()
    waiting_for_ad_cost = State()

    # -------------------------------------------------
    # Backward compatibility с СТАРЫМИ хендлерами промокодов
    # чтобы не падало на декораторах вида AdminStates.promo_waiting_*
    # -------------------------------------------------

    # Старый «одиночный» промокод:
    #   @router.message(AdminStates.promo_waiting_type)
    #   @router.message(AdminStates.promo_waiting_code)
    #   @router.message(AdminStates.promo_waiting_value)
    promo_waiting_type = State()
    promo_waiting_code = State()
    promo_waiting_value = State()

    # Старый «массовый» промокод:
    #   @router.message(AdminStates.bulk_promo_waiting_input)
    bulk_promo_waiting_input = State()