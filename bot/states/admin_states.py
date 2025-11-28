from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    # -----------------------------
    # Broadcast
    # -----------------------------
    waiting_for_broadcast_message = State()
    confirming_broadcast = State()

    # -----------------------------
    # User management
    # -----------------------------
    waiting_for_user_id_to_ban = State()
    waiting_for_user_id_to_unban = State()
    waiting_for_user_id_for_logs = State()
    waiting_for_user_search = State()
    waiting_for_subscription_days_to_add = State()
    waiting_for_direct_message_to_user = State()
    waiting_for_user_delete_confirmation = State()

    # -----------------------------
    # Ads campaigns
    # -----------------------------
    waiting_for_ad_source = State()
    waiting_for_ad_start_param = State()
    waiting_for_ad_cost = State()

    # -------------------------------------------------
    # 🔥 FULL BACKWARD COMPATIBILITY WITH OLD PROMO FLOW
    # -------------------------------------------------

    # OLD PROMO (single)
    promo_waiting_type = State()                # выбор типа: скидка / бонус
    promo_waiting_value = State()               # ввод процента или бонусных дней
    promo_waiting_plan_months = State()         # ввод месяцев (1/3/6/12) — новый старый
    promo_waiting_max_activations = State()     # ввод max активаций
    promo_waiting_expire = State()              # ввод количества дней действия
    promo_waiting_code = State()                # ввод текста промокода

    # OLD BULK PROMO
    bulk_promo_waiting_input = State()

    # -------------------------------------------------
    # (These may be unused now, but kept for compatibility)
    # Existing promo edit flow (if used)
    # -------------------------------------------------
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