
  
# Remnawave Subscription Sales Telegram Bot

This Telegram bot is designed to automate the sale and management of subscriptions for a **Remnawave panel**. It integrates with the Remnawave API for user and subscription management and uses YooKassa for processing payments.

## ✨ Features

* **User Interaction:**
    * User registration with language selection (English/Russian).
    * Display of main menu with available actions via inline keyboards.
    * Ability for users to view their current subscription status, expiration date, and configuration link.
    * Trial subscription system for new users (configurable, manual activation via button).
    * Promo code system for users to apply discounts or bonuses.
    * Referral program for users to earn bonus subscription days.
* **Subscription Management:**
    * Handles subscription purchases for various periods (1, 3, 6, 12 months).
    * Integrates with **YooKassa** for payment processing, including fiscal receipt data.
    * Automatic subscription activation/extension upon successful payment.
    * Link and syncs users with a **Remnawave panel** account, primarily matching by Telegram ID.
    * Updates user status, expiration dates, traffic limits, and inbounds on the Remnawave panel.
* **Admin Panel:**
    * Protected by `ADMIN_IDS` (supports multiple administrators).
    * **Statistics:** View bot usage (total users, banned, active subscriptions), recent payments, and panel sync status.
    * **User Management:**
        * Ban/Unban users by Telegram ID or @username (updates local DB and panel).
        * View a paginated list of banned users.
        * View a "user card" with detailed information and unban option.
    * **Broadcast:** Send messages to all users, users with active subscriptions, or users with expired subscriptions.
    * **Promo Codes:** Create and view promo codes (bonus days, activation limits, validity).
    * **Panel Sync:** Manually trigger synchronization of users and subscriptions from the Remnawave panel to the bot's database, matching by Telegram ID.
    * **Activity Logs:** View a paginated list of all user actions (messages, commands, callbacks) or logs for a specific user.
* **Notifications:**
    * Automated daily notifications to users about expiring subscriptions (via APScheduler).
    * Notifications to users and inviters upon successful referral bonus application.
    * Notifications to admin(s) about suspicious promo code input attempts.
* **Security & Technical:**
    * Uses parameterized queries to prevent SQL injection.
    * Proactive check for suspicious input in promo code field (notifies admin).
    * Middleware for checking banned users on every interaction.
    * Middleware for logging user actions.
    * Webhook support for Telegram and YooKassa for efficient updates.
    * Configurable via `.env` file.
    * Dockerized for easy deployment.

## 🚀 Technologies Used

* **Python 3.11**
* **Aiogram 3.x:** Asynchronous Telegram Bot Framework
* **aiohttp:** For running the webhook server
* **aiosqlite:** Asynchronous SQLite database interaction
* **YooKassa SDK:** For payment processing
* **APScheduler:** For scheduled tasks (e.g., notifications)
* **Pydantic:** For settings management (loading from `.env`)
* **Docker & Docker Compose:** For containerization and deployment

## ⚙️ Setup and Configuration

### Prerequisites

* Docker and Docker Compose installed.
* A running instance of a Remnawave panel.
* A Telegram Bot Token.
* A YooKassa Shop ID and Secret Key.

### Configuration Steps

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/machka-pasla/remnawave-tg-shop
    cd remnawave-tg-shop
    ```

2.  **Create an `.env` File:**
    Copy the `env.example` file to `.env` and fill in your specific values:
    ```bash
    cp .env.example .env
    nano .env 
    ```
    Key variables to configure in `.env`:
    * `BOT_TOKEN`: Your Telegram Bot Token from BotFather.
    * `ADMIN_IDS`: Comma-separated list of your Telegram User IDs for admin access (e.g., `12345678,98765432`). **Crucial for bot management.**
    * `DEFAULT_LANGUAGE`: Default language for new users (e.g., `ru` or `en`).
    * `DEFAULT_CURRENCY_SYMBOL`: e.g., `RUB`, `USD`.
    * `SUPPORT_LINK`: (Optional) URL for a support chat/contact (e.g., `https://t.me/your_support`).
    * `SERVER_STATUS_URL`: (Optional) URL to a server status page (e.g., Uptime Kuma).
    * **YooKassa Settings:**
        * `YOOKASSA_SHOP_ID`: Your shop ID from YooKassa.
        * `YOOKASSA_SECRET_KEY`: Your secret key from YooKassa.
        * `YOOKASSA_WEBHOOK_BASE_URL`: Your publicly accessible HTTPS base URL where the bot will listen for YooKassa webhooks (e.g., `https://your.domain.com`). The full path will be `{YOOKASSA_WEBHOOK_BASE_URL}/webhook/yookassa`.
        * `YOOKASSA_RETURN_URL`: (Optional) URL user is redirected to after payment, often `https://t.me/your_bot_username`.
        * `YOOKASSA_DEFAULT_RECEIPT_EMAIL`: **Important for 54-FZ (Russian fiscalization).** A default email for sending fiscal receipts.
        * `YOOKASSA_VAT_CODE`: VAT code for items in receipt (e.g., `1` for "No VAT". Consult YooKassa documentation and tax advisor).
        * `YOOKASSA_PAYMENT_MODE`: e.g., `full_prepayment`.
        * `YOOKASSA_PAYMENT_SUBJECT`: e.g., `service`.
    * `TELEGRAM_WEBHOOK_BASE_URL`: (Optional) If you want Telegram updates via webhook. Can be the same as `YOOKASSA_WEBHOOK_BASE_URL`. If not set, the bot will use polling for Telegram updates.
    * `PRICE_X_MONTH`: Prices for different subscription durations.
    * **Panel API Settings:**
        * `PANEL_API_URL`: Full URL to your Remnawave panel's API (e.g., `http://localhost:3000/api` or `https://panel.yourdomain.com/api`).
        * `PANEL_API_KEY`: API Key for authenticating with the Remnawave panel.
    * `PANEL_USER_DEFAULT_INBOUND_UUIDS`: (Optional) Comma-separated list of inbound UUIDs from your panel to assign to users. If empty, `activateAllInbounds: true` (panel default) is used for new users.
    * `TRIAL_ENABLED`, `TRIAL_DURATION_DAYS`, `TRIAL_TRAFFIC_LIMIT_GB`: Settings for the trial period.
    * `WEB_SERVER_HOST`, `WEB_SERVER_PORT`: Host and port for the bot's internal webhook server.
    * `LOGS_PAGE_SIZE`: For admin panel log pagination.

3.  **Locales:**
    * Translation files are in the `locales/` directory (`en.json`, `ru.json`). Ensure they are present and correctly formatted. The `bot_database.sqlite3` and `locales` directory will be mounted as volumes in Docker. `locales` mounting is optional.

4.  **Build and Run with Docker Compose:**
    ```bash
    docker compose up --build -d
    ```
    This command will build the Docker image (if it doesn't exist or if `Dockerfile` changed) and start the `vpn-shop` service in detached mode.

5.  **Webhook Setup (Important if using webhooks):**
    * **Reverse Proxy (Nginx, Caddy, etc.):** You need a reverse proxy to handle incoming HTTPS traffic, manage SSL certificates (e.g., from Let's Encrypt), and forward requests to your bot's container.
        * Forward requests for `https://{YOOKASSA_WEBHOOK_BASE_URL_domain}/webhook/yookassa` to `http://vpn-shop:{WEB_SERVER_PORT}/webhook/yookassa` (where `vpn-shop` is the service name in `docker-compose.yml`).
        * If using Telegram webhooks, forward requests for `https://{TELEGRAM_WEBHOOK_BASE_URL_domain}/<YOUR_BOT_TOKEN>` to `http://vpn-shop:{WEB_SERVER_PORT}/<YOUR_BOT_TOKEN>`.
    * **Telegram Webhook Registration:** The bot attempts to set its Telegram webhook URL on startup if `TELEGRAM_WEBHOOK_BASE_URL` is configured in `.env`. Check the bot logs to confirm if this was successful. You can also manually check using the Telegram Bot API method `getWebhookInfo`.

6.  **Database:**
    * A SQLite database file (`bot_database.sqlite3`) will be created in your project root (or wherever you map the volume). The schema is initialized automatically on the first run if the file doesn't exist.

7.  **Viewing Logs:**
    ```bash
    docker compose logs -f vpn-shop
    ```

## 🐳 Docker Setup

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Consider adding build arguments for proxy if needed in your environment
# ARG HTTP_PROXY
# ARG HTTPS_PROXY
# ENV http_proxy=$HTTP_PROXY
# ENV https_proxy=$HTTPS_PROXY

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure main.py is executable if needed, though python command handles it
# RUN chmod +x main.py

CMD ["python", "main.py"]

```

### `docker-compose.yml`

YAML

```
services:
  vpn-shop:
    build: .
    container_name: vpn-shop
    hostname: vpn-shop
    env_file:
      - .env
    networks:
      - remnawave-network # Ensure this external network exists or define it
    volumes:
      - ./bot_database.sqlite3:/app/bot_database.sqlite3
    #   - ./locales:/app/locales
    restart: unless-stopped
    # Optionally, expose ports if you are not using a shared Docker network
    # and want to access the bot's webserver directly (not recommended for production without a reverse proxy)
    # ports:
    #   - "8080:8080" 

networks:
  remnawave-network:
    external: true # Assumes 'remnawave-network' is an existing external Docker network
                   # If not, you might want to define it here or use a default bridge.

```

**Note on `remnawave-network`:** The `docker-compose.yml` assumes an external network named `remnawave-network`. If this network doesn't exist or you want the bot on a different network (e.g., a default bridge or a new one defined in this compose file), you'll need to adjust the `networks` section. If the Remnawave panel is also running in Docker on the same host, putting them on the same user-defined network allows them to communicate using service names.

## 🛠️ Project Structure (Overview)

```
.
├── bot/
│   ├── filters/          # Custom Aiogram filters (e.g., AdminFilter)
│   ├── handlers/         # Message and callback query handlers (admin and user)
│   ├── keyboards/        # Inline and reply keyboard generators
│   ├── middlewares/      # Custom Aiogram middlewares (i18n, ban check, logger)
│   ├── services/         # Business logic (payments, subscriptions, panel API interaction)
│   ├── states/           # FSM states
│   └── main_bot.py       # Core bot logic, dispatcher setup, startup/shutdown
├── config/
│   └── settings.py       # Pydantic settings model
├── db/
│   └── database.py       # Database schema, connection, and CRUD functions
├── locales/              # Localization files (en.json, ru.json)
├── .env.example          # Example environment variables
├── .env                  # Your local environment variables (ignored by git)
├── Dockerfile            # Instructions to build the Docker image
├── docker-compose.yml    # Docker Compose configuration
├── requirements.txt      # Python dependencies
└── main.py               # Main entry point to run the bot

```

## 🤝 Contributing

Contributions are welcome! 

## 🔮 Future Enhancements

-   More detailed analytics for admin.
-   Support for different payment methods.
-   Advanced promo code types (e.g., percentage discounts).

## Donations (pls)
- Russian and international cards [LINK](https://t.me/tribute/app?startapp=dqdg)
