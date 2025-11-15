from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import insert
import pandas as pd
from pathlib import Path
import httpx
import json
import time
from datetime import datetime
from models.products import ProductBase
from models.webhooks import Webhook, WebhookBase

class DatabaseOperations:
    upload_progress = 0.0

    def __init__(self, supabase_project_url: str = None, supabase_service_key: str = None):
        """
        Initialize with Supabase connection details.
        """
        self.supabase_project_url = supabase_project_url
        self.supabase_service_key = supabase_service_key
        self.engine = None
        self.SessionLocal = None

    def init_database(self, connection_string: str = None, 
                     project_url: str = None, 
                     service_key: str = None,
                     db_password: str = None):
        """
        Initialize database connection to Supabase.
        """
        try:
            if connection_string:
                conn_str = connection_string
            
            # Method 2: Build from project_url and password
            elif project_url and db_password:
                project_ref = project_url.replace('https://', '').replace('http://', '').split('.')[0]
                conn_str = f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"
            
            # Method 3: Use instance variables
            elif self.supabase_project_url and hasattr(self, 'db_password'):
                project_ref = self.supabase_project_url.replace('https://', '').replace('http://', '').split('.')[0]
                conn_str = f"postgresql://postgres:{self.db_password}@db.{project_ref}.supabase.co:5432/postgres"
            
            else:
                raise ValueError(
                    "Please provide connection details using one of these methods:\n"
                    "1. connection_string='postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres'\n"
                    "2. project_url='https://xxxxx.supabase.co' and db_password='your_password'\n"
                    "\nGet connection string from: Supabase Dashboard > Project Settings > Database > Connection String (URI)"
                )
            
            # Add SSL parameters if not already in connection string
            if "sslmode" not in conn_str.lower():
                conn_str += "?sslmode=require"
            
            # Create engine with optimized settings for Supabase
            self.engine = create_engine(
                conn_str,
                echo=False,
                pool_pre_ping=True,  # Verify connections before using
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600,  # Recycle connections after 1 hour
                pool_timeout=30,
                connect_args={
                    "connect_timeout": 10,
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 5,
                }
            )
            
            self.SessionLocal = sessionmaker(bind=self.engine)
            
            # Test connection
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT current_database(), current_user"))
                db_name, db_user = result.fetchone()
                print(f"Connected to Supabase database: {db_name} as user: {db_user}")
            
            print(f"Database connection established successfully")
            return True

        except SQLAlchemyError as e:
            print(f"Database initialization error: {str(e)}")
            print("\nTroubleshooting:")
            print("1. Verify your connection string is correct")
            print("2. Check database password")
            print("3. Ensure your IP is allowed (Supabase > Project Settings > Database > Connection Pooling)")
            raise

    def create_tables(self):
        """Creates ORM tables for both Products and Webhooks."""
        if not self.engine:
            raise RuntimeError("Engine not initialized. Call init_database() first.")

        try:
            ProductBase.metadata.create_all(self.engine)
            WebhookBase.metadata.create_all(self.engine)
            
            print("All tables created successfully (products, webhooks)")
        except Exception as e:
            print(f"Error creating tables: {str(e)}")
            raise

    def get_session(self):
        """Provides a database session."""
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    def get_products_paginated(self, page: int = 1, page_size: int = 50, 
                               search: str = None, status: int = None,
                               table_name: str = "products"):
        """
        Retrieve products with pagination, search, and filtering.
        """
        if not hasattr(self, "engine") or self.engine is None:
            raise RuntimeError("Engine not initialized. Call init_database() first.")

        offset = (page - 1) * page_size

        base_query = f'SELECT * FROM "{table_name}"'
        count_query = f'SELECT COUNT(*) as total FROM "{table_name}"'
        
        conditions = []
        params = {}
        
        if status is not None:
            conditions.append("status = :status")
            params["status"] = status
            
        if search:
            conditions.append(
                "(sku ILIKE :search OR name ILIKE :search OR description ILIKE :search)"
            )
            params["search"] = f"%{search}%"
        
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
            base_query += where_clause
            count_query += where_clause
        
        base_query += " ORDER BY sku LIMIT :limit OFFSET :offset"
        params["limit"] = page_size
        params["offset"] = offset

        with self.engine.connect() as conn:
            total_result = conn.execute(text(count_query), params).fetchone()
            total = total_result[0] if total_result else 0
            
            result = conn.execute(text(base_query), params)
            columns = result.keys()
            data = [dict(zip(columns, row)) for row in result.fetchall()]
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return {
            "data": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    
    def get_product_by_sku(self, sku: str, table_name: str = "products"):
        """
        Get a single product by SKU.
        """
        if not hasattr(self, "engine") or self.engine is None:
            raise RuntimeError("Engine not initialized. Call init_database() first.")
        
        query = text(f'SELECT * FROM "{table_name}" WHERE sku = :sku')
        
        with self.engine.connect() as conn:
            result = conn.execute(query, {"sku": sku}).fetchone()
            
            if result:
                columns = result._mapping.keys()
                return dict(zip(columns, result))
            return None
    
    def update_product_status(self, sku: str, status: int, table_name: str = "products"):
        """
        Update product status by SKU.
        """
        if not hasattr(self, "engine") or self.engine is None:
            raise RuntimeError("Engine not initialized. Call init_database() first.")
        
        query = text(f"""
            UPDATE "{table_name}" 
            SET status = :status 
            WHERE sku = :sku
        """)
        
        with self.engine.begin() as conn:
            result = conn.execute(query, {"sku": sku, "status": status})
            return result.rowcount > 0
    
    def delete_product(self, sku: str, table_name: str = "products"):
        """
        Delete a product by SKU.
        """
        if not hasattr(self, "engine") or self.engine is None:
            raise RuntimeError("Engine not initialized. Call init_database() first.")
        
        query = text(f'DELETE FROM "{table_name}" WHERE sku = :sku')
        
        with self.engine.begin() as conn:
            result = conn.execute(query, {"sku": sku})
            return result.rowcount > 0
    
    def upload_csv(self, csv_path: str, table_name: str = "products", chunksize: int = 500):
        """
        Upload CSV into Supabase PostgreSQL in chunks.
        """

        if not hasattr(self, "engine") or self.engine is None:
            raise RuntimeError("Engine not initialized. Call init_database() first.")

        print(f"Starting CSV upload to Supabase: {csv_path}")

        metadata = MetaData()
        metadata.reflect(bind=self.engine)

        if table_name not in metadata.tables:
            raise ValueError(f"Table '{table_name}' does not exist in Supabase.")

        product_table = metadata.tables[table_name]

        db_columns = [col.name for col in product_table.columns]

        expected_csv_columns = [c for c in db_columns if c != 'status']

        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        # -------- VALIDATE CSV HEADER --------
        header = pd.read_csv(csv_path, nrows=0)
        csv_cols = header.columns.tolist()

        missing = set(expected_csv_columns) - set(csv_cols)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        extra = set(csv_cols) - set(expected_csv_columns)
        if extra:
            raise ValueError(f"Unknown extra columns: {extra}")

        reorder_required = (csv_cols != expected_csv_columns)
        if reorder_required:
            print("⚠ Reordering CSV columns to match database schema")
        else:
            print("✓ CSV columns are in correct order")

        # -------- TOTAL ROWS (for progress %) --------
        total_rows = sum(1 for _ in open(csv_path, "r")) - 1
        if total_rows <= 0:
            raise ValueError("CSV contains no data rows.")

        inserted_rows = 0
        self.upload_progress = 0.0
        print(f"Total rows to process: {total_rows}")
        print(f"Processing in chunks of {chunksize} rows...")

        # -------- PROCESS IN CHUNKS WITH ROBUST RETRY LOGIC --------
        max_retries = 5
        chunk_num = 0
        
        for chunk in pd.read_csv(csv_path, chunksize=chunksize):
            chunk_num += 1

            if reorder_required:
                chunk = chunk[expected_csv_columns]

            chunk['status'] = 1
            
            # Remove duplicate SKUs within the chunk
            chunk = chunk.drop_duplicates(subset=['sku'], keep='last')
            
            if len(chunk) == 0:
                continue  # Skip empty chunks after deduplication

            rows = chunk.to_dict(orient="records")

            # Retry logic for this chunk
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    # Create a fresh connection for each chunk to avoid stale connections
                    with self.engine.connect() as conn:
                        with conn.begin():
                            # Use PostgreSQL's INSERT...ON CONFLICT for upsert
                            stmt = insert(product_table).values(rows)
                            
                            # Update all columns EXCEPT sku (primary key) and status (preserve existing)
                            update_dict = {col: stmt.excluded[col] for col in expected_csv_columns if col != "sku"}
                            
                            upsert_stmt = stmt.on_conflict_do_update(
                                index_elements=['sku'],
                                set_=update_dict
                            )
                            
                            # Execute the batch upsert
                            conn.execute(upsert_stmt)
                    
                    # Success - mark as complete
                    success = True
                    
                except (SQLAlchemyError, Exception) as e:
                    retry_count += 1
                    error_msg = str(e)
                    
                    if retry_count >= max_retries:
                        print(f"Failed to upload chunk {chunk_num} after {max_retries} attempts")
                        print(f"Error: {error_msg}")
                        raise Exception(f"Upload failed at chunk {chunk_num}/{int(total_rows/chunksize)}: {error_msg}")
                    
                    print(f"Connection error on chunk {chunk_num}, retrying ({retry_count}/{max_retries})...")

                    wait_time = min(2 ** retry_count + (retry_count * 0.5), 30)
                    time.sleep(wait_time)

                    try:
                        self.engine.dispose()
                    except:
                        pass

            # --- PROGRESS UPDATE (0.0 to 1.0) ---
            inserted_rows += len(rows)
            self.upload_progress = round(inserted_rows / total_rows, 4)
            
            # Print progress every 20 chunks
            if chunk_num % 20 == 0:
                print(f"Progress: {inserted_rows}/{total_rows} rows ({self.upload_progress * 100:.1f}%) - Chunk {chunk_num}")

            time.sleep(0.05)
        
        print(f"\nUpload completed: {inserted_rows}/{total_rows} rows processed successfully")
        self.upload_progress = 1.0

    def delete_all_rows(self, table_name: str = "products"):
        """
        Delete all rows from the specified table.
        """
        if not self.engine:
            raise RuntimeError("Engine not initialized. Call init_database() first.")

        metadata = MetaData()
        metadata.reflect(bind=self.engine)

        if table_name not in metadata.tables:
            raise ValueError(f"Table '{table_name}' does not exist.")

        table = metadata.tables[table_name]

        with self.SessionLocal() as session:
            try:
                deleted_count = session.execute(table.delete())
                session.commit()
                print(f"Deleted {deleted_count.rowcount} rows from {table_name} table")
            except Exception as e:
                session.rollback()
                print(f"Error deleting rows: {e}")
                raise
    
    def delete_products_by_sku(self, sku_list: list, table_name: str = "products"):
        """
        Delete multiple products by a list of SKUs.
        """
        if not sku_list:
            print("No SKUs provided")
            return 0

        if not self.engine:
            raise RuntimeError("Engine not initialized. Call init_database() first.")

        metadata = MetaData()
        metadata.reflect(bind=self.engine)

        if table_name not in metadata.tables:
            raise ValueError(f"Table '{table_name}' does not exist.")

        table = metadata.tables[table_name]

        with self.SessionLocal() as session:
            try:
                deleted_result = session.execute(
                    table.delete().where(table.c.sku.in_(sku_list))
                )
                session.commit()
                print(f"✓ Deleted {deleted_result.rowcount} rows from {table_name} table")
                return deleted_result.rowcount
            except Exception as e:
                session.rollback()
                print(f"Error deleting SKUs: {e}")
                raise

    def add_product(
        self, 
        sku: str, 
        name: str, 
        description: str, 
        status: int = 1, 
        table_name: str = "products"
    ) -> bool:
        """
        Add a single product to Supabase.
        """
        if not hasattr(self, "engine") or self.engine is None:
            raise RuntimeError("Engine not initialized. Call init_database() first.")

        query = text(f"""
            INSERT INTO "{table_name}" (sku, name, description, status)
            VALUES (:sku, :name, :description, :status)
            ON CONFLICT (sku) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                status = EXCLUDED.status
        """)

        try:
            with self.engine.begin() as conn:
                conn.execute(query, {
                    "sku": sku,
                    "name": name,
                    "description": description,
                    "status": status
                })
            print(f"Product '{sku}' added/updated successfully")
            return True
        except Exception as e:
            print(f"Failed to add/update product '{sku}': {e}")
            raise
    
    # =====================================================
    # WEBHOOK CRUD OPERATIONS
    # =====================================================
    
    def create_webhook(self, name: str, url: str, event_type: str, enabled: bool = True, 
                      secret_key: str = None, headers: dict = None):
        """Create a new webhook configuration in Supabase"""
        with self.SessionLocal() as session:
            webhook = Webhook(
                name=name,
                url=url,
                event_type=event_type,
                enabled=enabled,
                secret_key=secret_key,
                headers=json.dumps(headers) if headers else None
            )
            session.add(webhook)
            session.commit()
            session.refresh(webhook)
            print(f"Webhook '{name}' created successfully")
            return webhook
    
    def get_webhooks(self):
        """Get all webhooks from Supabase"""
        with self.SessionLocal() as session:
            webhooks = session.query(Webhook).all()
            return [
                {
                    "id": w.id,
                    "name": w.name,
                    "url": w.url,
                    "event_type": w.event_type,
                    "enabled": w.enabled,
                    "created_at": w.created_at.isoformat(),
                    "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None,
                    "last_status_code": w.last_status_code,
                    "last_response_time": w.last_response_time
                }
                for w in webhooks
            ]
    
    def update_webhook(self, webhook_id: int, **kwargs):
        """Update webhook configuration"""
        with self.SessionLocal() as session:
            webhook = session.query(Webhook).filter(Webhook.id == webhook_id).first()
            if not webhook:
                print(f"Webhook {webhook_id} not found")
                return None
            
            for key, value in kwargs.items():
                if hasattr(webhook, key):
                    setattr(webhook, key, value)
            
            webhook.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(webhook)
            print(f"✓ Webhook {webhook_id} updated successfully")
            return webhook
    
    def delete_webhook(self, webhook_id: int):
        """Delete a webhook"""
        with self.SessionLocal() as session:
            webhook = session.query(Webhook).filter(Webhook.id == webhook_id).first()
            if webhook:
                session.delete(webhook)
                session.commit()
                print(f"✓ Webhook {webhook_id} deleted successfully")
                return True
            print(f"⚠️  Webhook {webhook_id} not found")
            return False
    
    async def trigger_webhooks(self, event_type: str, payload: dict):
        """Trigger all enabled webhooks for a specific event type"""
        with self.SessionLocal() as session:
            webhooks = session.query(Webhook).filter(
                Webhook.event_type == event_type,
                Webhook.enabled == True
            ).all()
            
            if not webhooks:
                print(f"No enabled webhooks found for event: {event_type}")
                return
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                for webhook in webhooks:
                    try:
                        start_time = time.time()
                        
                        headers = {"Content-Type": "application/json"}
                        if webhook.headers:
                            headers.update(json.loads(webhook.headers))

                        if webhook.secret_key:
                            import hmac
                            import hashlib
                            signature = hmac.new(
                                webhook.secret_key.encode(),
                                json.dumps(payload).encode(),
                                hashlib.sha256
                            ).hexdigest()
                            headers["X-Webhook-Signature"] = signature
                        
                        response = await client.post(
                            webhook.url,
                            json=payload,
                            headers=headers
                        )
                        
                        response_time = int((time.time() - start_time) * 1000)
                        
                        webhook.last_triggered_at = datetime.utcnow()
                        webhook.last_status_code = response.status_code
                        webhook.last_response_time = response_time
                        session.commit()
                        
                        print(f"Webhook '{webhook.name}' triggered successfully (HTTP {response.status_code}, {response_time}ms)")
                        
                    except Exception as e:
                        print(f"Webhook '{webhook.name}' failed: {str(e)}")
                        webhook.last_status_code = 0
                        webhook.last_response_time = 0
                        session.commit()
    
    async def test_webhook(self, webhook_id: int):
        """Test a webhook with sample data"""
        with self.SessionLocal() as session:
            webhook = session.query(Webhook).filter(Webhook.id == webhook_id).first()
            if not webhook:
                print(f"Webhook {webhook_id} not found")
                return None
            
            test_payload = {
                "event": webhook.event_type,
                "test": True,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {"message": "This is a test webhook from Supabase"}
            }
            
            try:
                start_time = time.time()
                
                headers = {"Content-Type": "application/json"}
                if webhook.headers:
                    headers.update(json.loads(webhook.headers))
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        webhook.url,
                        json=test_payload,
                        headers=headers
                    )
                
                response_time = int((time.time() - start_time) * 1000)
                
                print(f"Test webhook completed (HTTP {response.status_code}, {response_time}ms)")
                
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "response_time": response_time,
                    "response_body": response.text[:500]
                }
            except Exception as e:
                print(f"Test webhook failed: {str(e)}")
                return {
                    "success": False,
                    "error": str(e)
                }
    
    def get_connection_info(self):
        """Get current connection information"""
        if not self.engine:
            return {"connected": False}
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        current_database() as database,
                        current_user as user,
                        version() as version,
                        inet_server_addr() as server_ip,
                        inet_server_port() as server_port
                """))
                row = result.fetchone()
                
                return {
                    "connected": True,
                    "database": row[0],
                    "user": row[1],
                    "version": row[2],
                    "server_ip": str(row[3]) if row[3] else "N/A",
                    "server_port": row[4]
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }
    
    def close(self):
        """Close database connection and cleanup"""
        if self.engine:
            self.engine.dispose()
            print("✓ Database connection closed")
