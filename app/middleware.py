import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.database import get_db_connection

logger = logging.getLogger(__name__)

class AdminImpersonationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        攔截 Request，處理 Admin 身分模擬與稽核防護。
        實作：從 Header 取得 `X-User-ID` 與可選的 `X-Impersonate-ID`。
        """
        user_id = request.headers.get("X-User-ID")
        impersonate_id = request.headers.get("X-Impersonate-ID")
        
        # 將實際使用者與目標使用者存入 request.state
        request.state.actor_user_id = user_id
        request.state.target_user_id = impersonate_id if impersonate_id else user_id
        request.state.is_impersonating = bool(impersonate_id and impersonate_id != user_id)

        # 這裡簡化判斷，實作中應去資料庫查證 `user_id` 的 role 是否為 'admin' 才能使用 `impersonate_id`
        
        response = await call_next(request)

        # 如果進入模擬狀態且執行變更資料之 Request (POST, PUT, DELETE)，寫入 Audit Logs
        if request.state.is_impersonating and request.method in ["POST", "PUT", "DELETE"]:
            # 背景寫入稽核日誌
            try:
                # 這裡使用簡單的新連線做 Logger，實務可利用 background tasks
                conn_generator = get_db_connection()
                conn = next(conn_generator)
                cur = conn.cursor()
                
                audit_query = """
                    INSERT INTO Audit_Logs (actor_user_id, target_user_id, action_detail)
                    VALUES (%s, %s, %s)
                """
                detail = f"{request.method} {request.url.path}"
                cur.execute(audit_query, (request.state.actor_user_id, request.state.target_user_id, detail))
                conn.commit()
                cur.close()
                # generator cleanup
                try:
                    next(conn_generator)
                except StopIteration:
                    pass
            except Exception as e:
                logger.error(f"Failed to insert Audit Log: {e}")

        return response
