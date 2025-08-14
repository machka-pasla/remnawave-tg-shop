"""
Database migration script to add phone_transfer_payments table
"""

import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from config.settings import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_phone_transfer_table():
    """Create the phone_transfer_payments table"""
    settings = get_settings()
    
    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL)
    
    async with engine.begin() as conn:
        # Check if table already exists
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'phone_transfer_payments'
            );
        """))
        
        table_exists = result.scalar()
        
        if table_exists:
            logger.info("Table phone_transfer_payments already exists. Skipping creation.")
            return
        
        # Create the table
        await conn.execute(text("""
            CREATE TABLE phone_transfer_payments (
                payment_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount FLOAT NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'RUB',
                subscription_duration_months INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                description TEXT,
                promo_code_id INTEGER,
                receipt_photo_id VARCHAR(255),
                receipt_file_id VARCHAR(255),
                admin_notes TEXT,
                rejection_reason TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE,
                approved_at TIMESTAMP WITH TIME ZONE,
                approved_by_admin_id BIGINT,
                rejected_at TIMESTAMP WITH TIME ZONE,
                rejected_by_admin_id BIGINT
            );
        """))
        
        # Create indexes
        await conn.execute(text("""
            CREATE INDEX idx_phone_transfer_payments_user_id ON phone_transfer_payments(user_id);
        """))
        
        await conn.execute(text("""
            CREATE INDEX idx_phone_transfer_payments_status ON phone_transfer_payments(status);
        """))
        
        # Add foreign key constraints
        await conn.execute(text("""
            ALTER TABLE phone_transfer_payments 
            ADD CONSTRAINT fk_phone_transfer_payments_user_id 
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;
        """))
        
        await conn.execute(text("""
            ALTER TABLE phone_transfer_payments 
            ADD CONSTRAINT fk_phone_transfer_payments_promo_code_id 
            FOREIGN KEY (promo_code_id) REFERENCES promo_codes(promo_code_id) ON DELETE SET NULL;
        """))
        
        logger.info("Table phone_transfer_payments created successfully with indexes and constraints.")
    
    await engine.dispose()


async def main():
    """Main migration function"""
    try:
        await create_phone_transfer_table()
        logger.info("Migration completed successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
