from fastapi import FastAPI, UploadFile, File, Query, HTTPException, WebSocket, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict
import concurrent.futures
import json
from datetime import datetime

from database.database import DatabaseOperations
from utility.loadData import CSVProductValidator

from utility.helper import broadcast_progress, active_connections

import asyncio
from pathlib import Path

import os
from dotenv import load_dotenv

load_dotenv()

executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)


# --- PYDANTIC MODELS ---
class StatusUpdate(BaseModel):
    status: int

class ProductResponse(BaseModel):
    sku: str
    name: str
    description: str
    status: int

class ProductCreate(BaseModel):
    sku: str = Field(..., description="Unique SKU for the product")
    name: str = Field(..., description="Product name")
    description: str = Field(..., description="Product description")
    status: int = Field(1, description="Product status (0=inactive, 1=active)")

class DeleteSKUsRequest(BaseModel):
    skus: List[str]

class WebhookCreate(BaseModel):
    name: str
    url: HttpUrl
    event_type: str
    enabled: bool = True
    secret_key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None

class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    event_type: Optional[str] = None
    enabled: Optional[bool] = None
    secret_key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None

# --- GLOBAL OBJECTS ---
csv_validator = CSVProductValidator()

async def lifespan(app: FastAPI):

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    connection_string = os.getenv("SUPABASE_DB_URL")
    print(f"supabase_url: {supabase_url}")
    print(f"supabase_key: {supabase_key}")
    print(f"connection_string: {connection_string}")
    db = DatabaseOperations(supabase_url, supabase_key)

    db.init_database(connection_string)
    db.create_tables()

    app.state.db = db

    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== WEBSOCKET ====================

@app.websocket("/ws/upload_progress")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    print(f"WebSocket connected. Total connections: {len(active_connections)}")
    
    try:
        # Keep connection alive and listen for messages
        while True:
            try:
                # Wait for any message (ping/pong to keep alive)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                # Send periodic progress updates
                if hasattr(app.state, 'db'):
                    progress = app.state.db.upload_progress
                    await websocket.send_json({
                        "progress": progress,
                        "percentage": round(progress * 100, 1)
                    })
                await asyncio.sleep(0.1)  # Update every 100ms for smooth progress
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print(f"WebSocket disconnected. Remaining connections: {len(active_connections)}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)


# ==================== PRODUCT ENDPOINTS ====================

@app.get("/products")
async def get_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    search: Optional[str] = Query(None, description="Search in SKU, name, or description"),
    status: Optional[int] = Query(None, ge=0, le=1, description="Filter by status (0=inactive, 1=active)")
):
    """
    Get paginated list of products with optional search and status filter.
    """
    try:
        db = app.state.db
        result = db.get_products_paginated(
            page=page,
            page_size=page_size,
            search=search,
            status=status
        )
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve products: {str(e)}")


@app.get("/products/{sku}")
async def get_product(sku: str):
    """
    Get a single product by SKU.
    """
    try:
        db = app.state.db
        product = db.get_product_by_sku(sku)
        
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with SKU '{sku}' not found")
        
        return product
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve product: {str(e)}")


@app.patch("/products/{sku}/status")
async def update_product_status(sku: str, status_update: StatusUpdate):
    """
    Update product status (0=inactive, 1=active).
    """
    if status_update.status not in [0, 1]:
        raise HTTPException(status_code=400, detail="Status must be 0 or 1")
    
    try:
        db = app.state.db
        updated = db.update_product_status(sku, status_update.status)
        
        if not updated:
            raise HTTPException(status_code=404, detail=f"Product with SKU '{sku}' not found")
        
        return {
            "status": "success",
            "message": f"Product status updated to {status_update.status}",
            "sku": sku
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")


@app.delete("/products/{sku}")
async def delete_product(sku: str):
    """
    Delete a product by SKU.
    """
    try:
        db = app.state.db
        deleted = db.delete_product(sku)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Product with SKU '{sku}' not found")
        
        return {
            "status": "success",
            "message": f"Product with SKU '{sku}' deleted",
            "sku": sku
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete product: {str(e)}")


# ==================== UPLOAD ENDPOINT ====================

@app.post("/upload_products_csv")
async def upload_products_csv(file: UploadFile = File(...)):
    """Upload products CSV with real-time progress tracking"""
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    
    # Create temp directory if it doesn't exist
    temp_dir = Path("temp_uploads")
    temp_dir.mkdir(exist_ok=True)
    
    # Save uploaded file
    file_path = temp_dir / file.filename
    
    try:
        # Save file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        print(f"File saved to: {file_path}")
        
        # Reset progress before starting
        app.state.db.upload_progress = 0.0
        await broadcast_progress(0.0)
        
        # Start upload in background task with progress monitoring
        async def upload_with_progress():
            try:
                # Run the upload in a separate thread to not block
                import threading
                
                def run_upload():
                    app.state.db.upload_csv(
                        csv_path=str(file_path),
                        table_name="products",
                        chunksize=2000  # Optimized for Supabase free tier
                    )
                
                upload_thread = threading.Thread(target=run_upload)
                upload_thread.start()
                
                # Monitor progress and broadcast updates
                last_progress = 0.0
                while upload_thread.is_alive():
                    current_progress = app.state.db.upload_progress
                    
                    # Only broadcast if progress changed significantly (> 0.5%)
                    if abs(current_progress - last_progress) >= 0.005:
                        await broadcast_progress(current_progress)
                        last_progress = current_progress
                    
                    await asyncio.sleep(0.1)  # Check every 100ms
                
                # Wait for thread to complete
                upload_thread.join()

                await broadcast_progress(1.0)
                
            except Exception as e:
                print(f"Upload error: {e}")
                raise
        
        # Run upload with progress tracking
        await upload_with_progress()
        
        return {
            "message": "CSV uploaded successfully",
            "filename": file.filename,
            "status": "completed",
            "progress": 1.0
        }
        
    except Exception as e:
        # Broadcast error state
        await broadcast_progress(0.0)
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )
    
    finally:
        # Clean up temp file
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                print(f"Failed to clean up temp file: {e}")


@app.delete("/delete_all_products")
async def delete_all_products():
    """
    Delete all products from the database.
    """
    try:
        db = app.state.db
        deleted_count = db.delete_all_rows()
        
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} products from the database"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete products: {str(e)}")


@app.delete("/delete_by_sku")
async def delete_products_by_sku(request: DeleteSKUsRequest):
    """
    Delete multiple products by a JSON list of SKUs.
    """
    try:
        sku_list = [sku.strip() for sku in request.skus if sku.strip()]
        if not sku_list:
            raise HTTPException(status_code=400, detail="No valid SKUs provided for deletion")

        db = app.state.db
        deleted_count = db.delete_products_by_sku(sku_list)

        return {
            "status": "success",
            "message": f"Deleted {deleted_count} products",
            "skus": sku_list
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete products: {str(e)}")


@app.post("/add_product")
async def add_product(product: ProductCreate):
    """
    Add a single product to the database.
    """
    db = app.state.db

    try:
        db.add_product(
            sku=product.sku,
            name=product.name,
            description=product.description,
            status=product.status
        )
        return {
            "status": "success",
            "message": f"Product '{product.sku}' added successfully",
            "product": product.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add product: {str(e)}")




# ==================== WEBHOOK ENDPOINTS ====================

@app.get("/webhooks")
async def get_webhooks():
    """Get all webhook configurations"""
    try:
        db = app.state.db
        webhooks = db.get_webhooks()
        return {"webhooks": webhooks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhooks")
async def create_webhook(webhook: WebhookCreate):
    """Create a new webhook configuration"""
    try:
        db = app.state.db
        new_webhook = db.create_webhook(
            name=webhook.name,
            url=str(webhook.url),
            event_type=webhook.event_type,
            enabled=webhook.enabled,
            secret_key=webhook.secret_key,
            headers=webhook.headers
        )
        return {"status": "success", "webhook": new_webhook}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/webhooks/{webhook_id}")
async def update_webhook(webhook_id: int, webhook: WebhookUpdate):
    """Update webhook configuration"""
    try:
        db = app.state.db
        update_data = {k: v for k, v in webhook.dict().items() if v is not None}
        if 'url' in update_data:
            update_data['url'] = str(update_data['url'])
        
        updated = db.update_webhook(webhook_id, **update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Webhook not found")
        
        return {"status": "success", "webhook": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: int):
    """Delete a webhook"""
    try:
        db = app.state.db
        deleted = db.delete_webhook(webhook_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Webhook not found")
        
        return {"status": "success", "message": "Webhook deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: int):
    """Test a webhook with sample data"""
    try:
        db = app.state.db
        result = await db.test_webhook(webhook_id)
        if not result:
            raise HTTPException(status_code=404, detail="Webhook not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Update existing endpoints to trigger webhooks
@app.post("/add_product")
async def add_product(product: ProductCreate):
    """Add a single product and trigger webhooks"""
    db = app.state.db
    
    try:
        db.add_product(
            sku=product.sku,
            name=product.name,
            description=product.description,
            status=product.status
        )
        
        # Trigger webhooks asynchronously
        await db.trigger_webhooks("product.created", {
            "event": "product.created",
            "timestamp": datetime.utcnow().isoformat(),
            "data": product.dict()
        })
        
        return {
            "status": "success",
            "message": f"Product '{product.sku}' added successfully",
            "product": product.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add product: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)